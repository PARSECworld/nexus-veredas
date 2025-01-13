from django.shortcuts import render, redirect
from .models import *
from .scripts import *
from .settings import *
from datetime import datetime
from pyproj import Transformer
import boto3, os

def collectionDetail(request, nexusArea, date):
    date_form = datetime.strptime(date, '%Y-%m-%d').date()
    try: col = ImageCollection.objects.get(nexusArea=nexusArea, date=date)
    except ImageCollection.DoesNotExist:
        return render(request, 'error.html', {'message': 'Erro: coleção inexistente.'})
    areas = list(ImageCollection.objects.values_list('nexusArea', flat=True).distinct())
    dates = list(ImageCollection.objects.values_list('date', flat=True).distinct())
    dates = [date.isoformat() for date in dates]
    
    imageData = []
    saveDirectory = f'images/outlines/{nexusArea}_{date}/'
    credentials = getCredentials(AWS_CREDENTIALS)
    s3_client = boto3.client('s3',
                aws_access_key_id=credentials['aws_access_key_id'],
                aws_secret_access_key=credentials['aws_secret_access_key'],
                region_name=S3_REGION)

    for image in col.images.all():
        url = s3_client.generate_presigned_url('get_object',
            Params={'Bucket': S3_BUCKET, 'Key': saveDirectory + image.outline.name},
            ExpiresIn=EXPIRATION)
        coord = getCoordinates(image.outline.name, url)
        epsg = getEpsgCode(image.outline.name, url)
        if coord and epsg:
            transformer = Transformer.from_crs(epsg, 'EPSG:4326', always_xy=True)
            coord['xMin'], coord['yMin'] = transformer.transform(coord['xMin'], coord['yMin'])
            coord['xMax'], coord['yMax'] = transformer.transform(coord['xMax'], coord['yMax'])
            coord['xMin'] = round(coord['xMin'], 5)
            coord['yMin'] = round(coord['yMin'], 5)
            coord['xMax'] = round(coord['xMax'], 5)
            coord['yMax'] = round(coord['yMax'], 5)
        imageData.append({'image': image, 'coordinates': coord})
    return render(request, 'collectionDetail.html', {'collection': col, 'areas': areas, 'dates': dates,
                                                      'images': imageData, 'date': date_form})

def list_collections(request):
    return render(request, 'collectionList.html', {'collections': ImageCollection.objects.all()})

def main(request):
    areas = list(ImageCollection.objects.values_list('nexusArea', flat=True).distinct())
    dates = list(ImageCollection.objects.values_list('date', flat=True).distinct())
    dates = [date.isoformat() for date in dates]
    return render(request, 'main.html', {'areas': areas, 'dates': dates, 'app_url': GOOGLE_EARTH_ENGINE_APP_URL})