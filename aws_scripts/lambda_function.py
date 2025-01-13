import boto3

INSTANCIA_DO_ALGORITMO = <Adicione Valor>
INSTANCIA_WEBSERVER = <Adicione Valor>
NOME_DO_PROJETO = <Adicione Valor>

ec2_client = boto3.client('ec2')
ssm_client = boto3.client('ssm')

def lambda_handler(event, context):

    # Inicia EC2 tcc-inpe-veredas-ubuntu
    ec2_client.start_instances(InstanceIds=[INSTANCIA_DO_ALGORITMO])
    print(f'Instância EC2 tcc-inpe-veredas-ubuntu ligada')
    
    # Espera até começar a rodar
    ec2_client.get_waiter('instance_running').wait(InstanceIds=[INSTANCIA_DO_ALGORITMO])
    print(f'Instância EC2 tcc-inpe-veredas-ubuntu rodando')

    # Envia imagens até o s3
    print(f'Iniciando o envio de imagens')
    command = 'python ec2tos3.py resultados images'
    response = ssm_client.send_command(
        InstanceIds=[INSTANCIA_DO_ALGORITMO],
        DocumentName="AWS-RunShellScript",
        Parameters={'commands': [command]},
    )

    # Espera o script terminar
    command_id = response['Command']['CommandId']

    while True:
        output = ssm_client.get_command_invocation(
            CommandId=command_id,
            InstanceId=INSTANCIA_DO_ALGORITMO
        )
        
        if output['Status'] == 'Success':
            print(output['StandardOutputContent'])
            break
        elif output['Status'] == 'Failed':
            print(output['StandardErrorContent'])
            break

        # Espera 5s antes de checar de novo
        time.sleep(5)

    # Desliga a instância
    ec2_client.stop_instances(InstanceIds=[INSTANCIA_DO_ALGORITMO])
    
    # Atualiza webserver
    print(f'Acionando o webserver')
    command = f'./{NOME_DO_PROJETO}/update_images.sh'
    response = ssm_client.send_command(
        InstanceIds=[INSTANCIA_WEBSERVER],
        DocumentName="AWS-RunShellScript",
        Parameters={'commands': [command]},
    )

    # Espera o script terminar
    command_id = response['Command']['CommandId']

    while True:
        output = ssm_client.get_command_invocation(
            CommandId=command_id,
            InstanceId=INSTANCIA_WEBSERVER
        )
        
        if output['Status'] == 'Success':
            print(output['StandardOutputContent'])
            break
        elif output['Status'] == 'Failed':
            print(output['StandardErrorContent'])
            break

        # Espera 5s antes de checar de novo
        time.sleep(5)  

    return {
        'statusCode': 200,
        'body': f"Fim"
    }