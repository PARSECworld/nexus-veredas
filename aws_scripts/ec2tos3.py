import boto3
import os
import sys

def load_credentials(path):
    credentials = {}
    try:
        with open(path, 'r') as f:
            for line in f:
                key, value = line.strip().split('=')
                credentials[key] = value
    except FileNotFoundError:
        print(f"Arquivo de credenciais {path} não encontrado.")
    except Exception as e:
        print(f"Ocorreu um erro ao ler o arquivo de credenciais: {e}")
    return credentials

def upload_to_s3(init_path, bucket, s3_path, aws_access_key_id, aws_secret_access_key):
    s3 = boto3.client(
        's3',
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )

    if os.path.isfile(init_path):
        try:
            s3.upload_file(init_path, bucket, s3_path)
            print(f"Arquivo {init_path} carregado para s3://{bucket}/{s3_path}")
        except Exception as e:
            print(f"Erro ao fazer upload do arquivo: {e}")
    elif os.path.isdir(init_path):
        for root, _, files in os.walk(init_path):
            for file in files:
                init_file_path = os.path.join(root, file)
                relative_path = os.path.relpath(init_file_path, init_path)
                s3_file_path = os.path.join(s3_path, relative_path).replace("\\", "/")   
                try:
                    s3.upload_file(init_file_path, bucket, s3_file_path)
                    print(f'Arquivo {init_file_path} enviado para {s3_file_path} no bucket {bucket}.')
                except Exception as e:
                    print(f"Erro ao fazer upload do arquivo: {e}")
    else:
        print(f"O caminho {init_path} não existe ou não é um arquivo/pasta válido.")

if __name__ == "__main__":
    if len(sys.argv) == 2: s3_path = os.path.basename(sys.argv[1])
    elif len(sys.argv) == 3: s3_path = sys.argv[2]
    else:
        print("Uso: python ec2tos3.py <caminho_local> <caminho_no_s3>")
        sys.exit(1)

    init_path = sys.argv[1]
    bucket = 'tcc-usp-inpe-veredas'
    keys = load_credentials('/home/ubuntu/awskeys.txt')

    if not keys['aws_access_key_id'] or not keys['aws_secret_access_key']:
        print("Credenciais AWS não encontradas.")
    else:
        upload_to_s3(init_path, bucket, s3_path, keys['aws_access_key_id'], keys['aws_secret_access_key'])
