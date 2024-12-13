from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndex
from azure.storage.blob import BlobServiceClient
from backend.settings import app_settings
import requests
import logging
from dotenv import load_dotenv
import os

# load env variabls
load_dotenv()

# Azure configuration
SEARCH_SERVICE_NAME = app_settings.datasource.service
ADMIN_KEY = app_settings.datasource.key
INDEX_NAME = app_settings.datasource.index
INDEXER_NAME = os.getenv("INDEXER_NAME")
STORAGE_ACCOUNT_NAME = os.getenv("STORAGE_ACCOUNT_NAME")
STORAGE_ACCOUNT_KEY = os.getenv("STORAGE_ACCOUNT_KEY")
BLOB_CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME")

# base URL
SEARCH_ENDPOINT = f"https://{SEARCH_SERVICE_NAME}.search.windows.net"
BLOB_ENDPOINT = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"

blob_service_client = BlobServiceClient(
    account_url=BLOB_ENDPOINT, credential=STORAGE_ACCOUNT_KEY
)


def upload_to_blob_storage(file):
    """Sube el archivo a Azure Blob Storage."""
    try:
        blob_client = blob_service_client.get_blob_client(
            container=BLOB_CONTAINER_NAME, blob=file.filename
        )
        blob_client.upload_blob(file.stream, overwrite=True)
        logging.info(f"File {file.filename} successfully uploaded to Blob Storage.")
    except Exception as e:
        logging.error(f"Failed to upload file to Blob Storage: {str(e)}")
        raise


def trigger_index_update():
    """Ejecuta el trigger del indexador de Azure Cognitive Search."""
    try:
        url = f"{SEARCH_ENDPOINT}/indexers/{INDEXER_NAME}/run?api-version=2020-06-30"
        headers = {"Content-Type": "application/json", "api-key": ADMIN_KEY}
        response = requests.post(url, headers=headers)

        if response.status_code != 202:
            raise ValueError(
                f"Failed to run indexer: {response.status_code}, {response.text}"
            )

        logging.info("Indexer triggered successfully.")
    except Exception as e:
        logging.error(f"Failed to trigger index update: {str(e)}")
        raise


def delete_all_blobs():
    """Deletes all blobs from the specified Azure Blob Storage container.
    Iterates through the blobs in the container and removes them one by one.
    """
    try:
        blob_service_client = BlobServiceClient(
            account_url=BLOB_ENDPOINT, credential=STORAGE_ACCOUNT_KEY
        )
        container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)

        logging.debug(f"Deleting blobs from container: {BLOB_CONTAINER_NAME}")
        blob_list = container_client.list_blobs()
        for blob in blob_list:
            logging.debug(f"Deleting blob: {blob.name}")
            container_client.delete_blob(blob.name)
        logging.debug("All blobs have been successfully deleted.")
    except Exception as e:
        logging.error(f"Error while deleting blobs: {e}")


def recreate_index():
    """Deletes an existing index and creates a new one in Azure Cognitive Search.
    Configures the index schema with specific fields such as `id`, `name`, `content`,
    and metadata like storage path, size, and last modification date.
    """
    try:
        index_client = SearchIndexClient(
            endpoint=SEARCH_ENDPOINT, credential=AzureKeyCredential(ADMIN_KEY)
        )

        # If exists, delete the index
        if INDEX_NAME in [idx.name for idx in index_client.list_indexes()]:
            index_client.delete_index(INDEX_NAME)

        # Create a new index
        logging.debug(f"Creating index: {INDEX_NAME}")
        fields = [
            {"name": "id", "type": "Edm.String", "key": True, "searchable": False},
            {"name": "name", "type": "Edm.String", "searchable": True},
            {"name": "content", "type": "Edm.String", "searchable": True},
            {
                "name": "metadata_storage_path",
                "type": "Edm.String",
                "searchable": False,
            },  # Ruta del blob
            {
                "name": "metadata_storage_size",
                "type": "Edm.Int64",
                "searchable": False,
            },  # Tamaño del archivo
            {
                "name": "metadata_storage_last_modified",
                "type": "Edm.DateTimeOffset",
                "searchable": False,
            },  # Última modificación
        ]
        index = SearchIndex(name=INDEX_NAME, fields=fields)
        index_client.create_index(index)
        logging.debug("Index successfully created.")
    except Exception as e:
        logging.error(f"Error while recreating the index: {e}")


def empty_index():
    """Clears the Azure Blob Storage container and recreates the index in Azure Cognitive Search.
    Combines the functionality of `delete_all_blobs` and `recreate_index`.
    """
    try:
        # Delete all blob from Azure Container
        logging.info("STARTING INDEX REMOVAL...")
        delete_all_blobs()

        # Recreate the index using Azure Search
        recreate_index()
        logging.info("INDEX EMPTIED SUCCESSFULLY.")
    except Exception as e:
        logging.error(f"Error in empty_index: {e}")
        raise
