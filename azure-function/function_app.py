import azure.functions as func
import logging

app = func.FunctionApp()

@app.blob_trigger(arg_name="myblob", path="form-uploads/{name}", connection="formstorageaa0408_STORAGE")
def BlobLogProcessor(myblob: func.InputStream):
    # This wakes up the moment a document is uploaded
    file_name = myblob.name
    file_size = myblob.length
    
    logging.info(f"SERVERLESS TRIGGER INITIATED: Python Azure Function processing new upload.")
    logging.info(f"File Name: {file_name}")
    logging.info(f"File Size: {file_size} bytes")
    
    # In a production environment, you could add code here to run OCR, 
    # scan for viruses, or update the Azure Table Storage records!