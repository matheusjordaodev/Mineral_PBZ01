from azure.storage.blob import BlobServiceClient, ContentSettings
import os
import uuid
from typing import Optional, List, Dict, Any

class AzureBlobService:
    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv()
        
        self.connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        self.container_name = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "media")
        
        if not self.connection_string:
            print("AVISO: AZURE_STORAGE_CONNECTION_STRING não encontrada no .env")
            # Fallback for unexpected failures where env is missing entirely, though it shouldn't be.
            self.connection_string = ""

        self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        self._ensure_container_exists()

    def _ensure_container_exists(self):
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            if not container_client.exists():
                try:
                    from azure.storage.blob import PublicAccess
                    container_client.create_container(public_access=PublicAccess.Blob)
                    print(f"Container '{self.container_name}' created with public access.")
                except Exception:
                    try:
                        # Storage Account may have anonymous access disabled; create without public access
                        container_client.create_container()
                        print(f"Container '{self.container_name}' created without public access.")
                    except Exception as ce:
                        print(f"Error creating container '{self.container_name}': {ce}")
                        raise
        except Exception as e:
            print(f"Error ensuring container exists: {e}")
            raise

    def upload_file(self, file_data: Any, blob_name: str, content_type: str = None) -> str:
        """
        Uploads a file to Azure Blob Storage and returns the URL.
        file_data: bytes or file-like object
        blob_name: full path/name for the blob (e.g. 'folder/file.jpg')
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=blob_name)

            # Set content settings if type is provided
            my_content_settings = ContentSettings(content_type=content_type) if content_type else None

            blob_client.upload_blob(file_data, overwrite=True, content_settings=my_content_settings)

            return blob_client.url
        except Exception as e:
            error_str = str(e)
            if "ContainerNotFound" in error_str or "container does not exist" in error_str.lower():
                # Container missing at upload time — try to create it and retry once
                try:
                    self._ensure_container_exists()
                    if hasattr(file_data, 'seek'):
                        file_data.seek(0)
                    blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=blob_name)
                    my_content_settings = ContentSettings(content_type=content_type) if content_type else None
                    blob_client.upload_blob(file_data, overwrite=True, content_settings=my_content_settings)
                    return blob_client.url
                except Exception as retry_e:
                    print(f"Error uploading file to Azure after container creation: {retry_e}")
                    raise retry_e
            print(f"Error uploading file to Azure: {e}")
            raise e

    def get_sas_url(self, blob_url: Optional[str], expiry_hours: int = 24) -> Optional[str]:
        """
        Retorna a URL original sem gerar SAS token, mantendo o link sempre público/disponível.
        A assinatura é mantida para não quebrar compatibilidade com código existente.
        """
        return blob_url

    def list_files(self) -> List[Dict[str, Any]]:
        """
        List blobs in the container.
        """
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            blob_list = container_client.list_blobs()
            files = []
            for blob in blob_list:
                files.append({
                    "name": blob.name,
                    "url": self.get_sas_url(container_client.get_blob_client(blob).url),
                    "size": blob.size,
                    "content_type": blob.content_settings.content_type
                })
            return files
        except Exception as e:
            print(f"Error listing files from Azure: {e}")
            return []
