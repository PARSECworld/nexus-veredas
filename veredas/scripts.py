from .models import *
from .settings import *
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from datetime import datetime
from django.core.files import File
from google.cloud import storage
from io import BytesIO
from PIL import Image as Img
from shapely.geometry import box
from concurrent.futures import ThreadPoolExecutor
import boto3, ee, geopandas, math, os, rasterio, requests, tempfile, unicodedata, logging, time

logger = logging.getLogger('django')

def getCredentials(file):
	credentials = {}
	try:
		with open(file, 'r') as f:
			for line in f:
				key, value = line.strip().split('=')
				credentials[key] = value
	except FileNotFoundError:
		logger.debug(f'Arquivo de credenciais {file} não encontrado.')
	except Exception as e:
		logger.debug(f'Ocorreu um erro ao ler o arquivo de credenciais: {e}')
	return credentials

def getCoordinates(key, path):
	if not key.endswith('.tif'): return None
	with rasterio.open(path) as src:
		if src.crs is not None:
			return {
				'xMin': src.bounds.left,
				'yMin': src.bounds.bottom,
				'xMax': src.bounds.right,
				'yMax': src.bounds.top
			}
		else: return None

def getEpsgCode(key, path):
	if not key.endswith('.tif'): return None
	with rasterio.open(path) as src:
		if src.crs is not None: return src.crs.to_string()
		else: return None

def parseImages(expiration):
	credentials = getCredentials(AWS_CREDENTIALS)
	s3client = boto3.client('s3',
					aws_access_key_id=credentials['aws_access_key_id'],
					aws_secret_access_key=credentials['aws_secret_access_key'],
					region_name=S3_REGION)
	try:
		response = s3client.list_objects_v2(Bucket=S3_BUCKET, Prefix='shapefiles')
	except (NoCredentialsError, PartialCredentialsError):
		logger.debug('Erro: credenciais incompletas.')
		return
	except Exception as e:
		logger.debug(f'Erro ao acessar o S3: {e}.')
		return

	shpfiles = {}
	for root, dirs, files in os.walk(f'{BASE_DIR}/shapefiles/'):
		for file in files:
			_, extension = os.path.splitext(file)
			fpath = os.path.join(root, file)
			shpfiles[extension] = fpath
	gdf = geopandas.read_file(shpfiles['.shp'])
	
	response = s3client.list_objects_v2(Bucket=S3_BUCKET, Prefix='images/')
	newCollections = []
	for key in [file['Key'] for file in response.get('Contents', [])]:
		if not key.endswith('.tif'): continue
		url = s3client.generate_presigned_url('get_object',
			Params={'Bucket': S3_BUCKET, 'Key': key},
			ExpiresIn=expiration)
		urlResponse = requests.get(url)
		if urlResponse.status_code != 200:
			logger.debug(f'Falha ao baixar o arquivo: status {urlResponse.status_code}.')
			continue
		coord = getCoordinates(key, url)
		if not coord:
			logger.debug(f'Não foi possível extrair as coordenadas do arquivo {key}.')
			continue
		epsg = getEpsgCode(key, url)
		if not epsg:
			logger.debug(f'Não foi possível extrair o código EPSG do arquivo {key}.')
			continue

		frame = box(coord['xMin'], coord['yMin'], coord['xMax'], coord['yMax'])
		imageShape = geopandas.GeoDataFrame({'geometry': [frame]}, crs=epsg).to_crs(epsg=4326)
		for _, row in gdf.iterrows():
			if row['geometry'].contains(imageShape.geometry.iloc[0].centroid):
				date = s3client.head_object(Bucket=S3_BUCKET, Key=key)['LastModified'].date()
				c, created = ImageCollection.objects.get_or_create(nexusArea=row[NEXUS_TITULO_COLUNA_NOME].replace(' ', '-'), date=date)
				if c not in newCollections: newCollections.append(c)
				i = Image.objects.create(imageCollection=c)
				i.outline.save(f'outline_{i.id}.tif', File(BytesIO(urlResponse.content)))
				i.save()
				xMin, yMin, xMax, yMax = imageShape.geometry.iloc[0].bounds
				obtainSatelliteImage(i, xMin, yMin, xMax, yMax)
				s3client.delete_object(Bucket=S3_BUCKET, Key=key)
				break
		else:
			logger.debug(f'Nenhuma área Nexus corresponde com s3://{S3_BUCKET}/{key}.')
	for collection in newCollections:
		uploadImageCollection(collection)

def obtainSatelliteImage(image, xMin, yMin, xMax, yMax):
	lon = (xMin + xMax)/2
	lat = (yMin + yMax)/2
	x = (xMax - xMin)*math.cos(math.radians(lat))
	y = yMax - yMin
	distMax = max(x, y)
	pPixel = distMax / 640 # distância por pixel; 640px = máx. no Google API
	z = math.floor(math.log2(360/256/pPixel)) # 1 tile = 256x256 px
	pPixel = 360 / 256 / 2 ** z
	p = math.ceil(distMax / pPixel)

	url = (
		f'https://maps.googleapis.com/maps/api/staticmap?'
		f'size={p}x{p}&maptype=satellite&zoom={z}&center={lat},{lon}&key={GOOGLE_MAPS_STATIC_API_KEY}'
	)

	response = requests.get(url)

	pngName = f'satelliteImage_{image.pk}.png'
	pngPath = f'{MEDIA_ROOT}/{pngName}'
	img = Img.open(BytesIO(response.content)).transpose(Img.FLIP_TOP_BOTTOM)
	cutH = math.floor(x/distMax*p)
	cutV = math.floor(y/distMax*p)
	left = math.floor((p-cutH)/2)
	right = p - left
	top = math.floor((p-cutV)/2)
	bottom = p - top
	img = img.crop((left, top, right, bottom))
	img.save(pngPath)

	with rasterio.open(pngPath) as dataset:
		bands = [1]
		west, south, east, north = (-180, -90, 180, 90)
		data = dataset.read(bands)
		transform = rasterio.transform.from_bounds(
			west, south, east, north, data.shape[2], data.shape[1]
		)
		kwargs = {
			'driver': 'GTiff',
			'width': data.shape[2],
			'height': data.shape[1],
			'count': len(bands),
			'dtype': data.dtype,
			'nodata': 0,
			'transform': transform,
			'crs': 'EPSG:4326'  
		}
		
		tifName = f"{pngName.split('.')[0]}.tif"
		tifPath = f'{MEDIA_ROOT}/{tifName}'
		
		with rasterio.open(tifPath, 'w', **kwargs) as tif:
			tif.write(data, indexes=bands)

	with open(tifPath, 'rb') as file:
		image.satelliteImage.save(tifName, File(file))

def norm(text):
	n = unicodedata.normalize('NFD', text)
	n = ''.join(c for c in n if not unicodedata.combining(c))
	n.replace(' ', '_')
	return n

def uploadImageCollection(imageCollection):

	executor = ThreadPoolExecutor(max_workers=50)

	def upload_to_storage(client, name, path):
		bucket = client.get_bucket(GOOGLE_CLOUD_STORAGE_BUCKET)
		blob = bucket.blob(name)
		blob.upload_from_filename(path)

	def upload_to_ee(client, folderId, fileName):
		assetId = f"{folderId}/{fileName.split('.')[0]}"
		gcloudUri = f'gs://{GOOGLE_CLOUD_STORAGE_BUCKET}/{fileName}'
		requestId = ee.data.newTaskId()[0]
		params = {
			'name': assetId,
			'tilesets': [{'sources': [{'uris': [gcloudUri]}]}]
		} 

		logger.debug(f'Upload de imagem {fileName}')
		response = ee.data.startIngestion(request_id=requestId, params=params)

		executor.submit(check_ingestion, response['id'], client, fileName)

	def check_ingestion(operationId, client, fileName):
		while True:
			operation = ee.data.getOperation(f"projects/{GOOGLE_API_PROJECT}/operations/{operationId}")
			if operation and 'metadata' in operation and 'state' in operation['metadata']:
				state = operation['metadata']['state']
				
				if state == 'SUCCEEDED':
					logger.debug(f'Imagem {fileName} enviada ao GEE com sucesso.')
					delete_from_storage(client, fileName)
					break
				elif state == 'FAILED':
					logger.debug(f'GEE não conseguiu ingerir {fileName}.')
					break
				else:
					logger.debug(f'Estado do GEE para o arquivo {fileName}: {state}')
			
			time.sleep(10)



	def delete_from_storage(client, name):
		bucket = client.get_bucket(GOOGLE_CLOUD_STORAGE_BUCKET)
		blob = bucket.blob(name)
		blob.delete()

	credentials = ee.ServiceAccountCredentials(GOOGLE_SERVICE_ACCOUNT, GOOGLE_PRIVATE_KEY_PATH.__str__())
	ee.Initialize(credentials)
	nArea = norm(imageCollection.nexusArea)
	folderOutlineId = f'projects/{GOOGLE_API_PROJECT}/assets/outlines_{nArea}_{imageCollection.date.year}-{imageCollection.date.month}-{imageCollection.date.day}'
	folderSatelliteImageId = f'projects/{GOOGLE_API_PROJECT}/assets/satelliteImages_{nArea}_{imageCollection.date.year}-{imageCollection.date.month}-{imageCollection.date.day}'

	policy = {
		'bindings': [
			{
				'role': 'roles/viewer',
				'members': ['allUsers']  
			}
		]
	}

	try:
		ee.data.createFolder(folderOutlineId)
		logger.debug(f'Criando folder {folderOutlineId}')
		ee.data.setIamPolicy(folderOutlineId, policy)
	except ee.ee_exception.EEException:
		logger.debug(f'{folderOutlineId} já existe.')
	try:
		ee.data.createFolder(folderSatelliteImageId)
		logger.debug(f'Criando folder {folderSatelliteImageId}')
		ee.data.setIamPolicy(folderSatelliteImageId, policy)
	except ee.ee_exception.EEException:
		logger.debug(f'{folderSatelliteImageId} já existe.')

	client = storage.Client.from_service_account_json(GOOGLE_PRIVATE_KEY_PATH.__str__())
	for image in imageCollection.images.all():
		outlineName = image.outlineName()
		satelliteImageName = image.satelliteImageName()
		upload_to_storage(client, outlineName, image.outline.path)
		upload_to_storage(client, satelliteImageName, image.satelliteImage.path)
		upload_to_ee(client, folderOutlineId, outlineName)
		upload_to_ee(client, folderSatelliteImageId, satelliteImageName)