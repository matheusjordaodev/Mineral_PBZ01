import sys
from pathlib import Path

# Adiciona a raiz do projeto ao PYTHONPATH para importar corretamente os módulos
sys.path.append(str(Path(__file__).parent))

from services.azure_blob_service import AzureBlobService

def run_test():
    print("Iniciando teste de upload para o Azure Blob Storage...")
    try:
        service = AzureBlobService()
        
        import uuid
        # Preparar os dados a serem enviados
        conteudo = "Olá mundo".encode('utf-8')
        nome_arquivo = f"teste_ola_mundo_{uuid.uuid4().hex[:8]}.txt"
        
        print(f"Fazendo upload do arquivo '{nome_arquivo}'...")
        
        # Fazer o upload do arquivo
        url = service.upload_file(conteudo, nome_arquivo, content_type="text/plain")
        
        print("Sucesso! Arquivo enviado com sucesso.")
        print(f"URL Original (Privada): {url}")
        
        # Gerar a URL com acesso temporário (SAS Token)
        sas_url = service.get_sas_url(url)
        print(f"URL Temporária (Válida por 24h): {sas_url}")
        
    except Exception as e:
        print(f"Erro durante o teste: {e}")

if __name__ == "__main__":
    run_test()
