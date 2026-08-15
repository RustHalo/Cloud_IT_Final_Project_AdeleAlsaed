from datetime import datetime
import os
from azure.storage.blob import BlobServiceClient
from azure.data.tables import TableServiceClient, TableEntity
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import bcrypt
from dotenv import load_dotenv
import re
from pydantic import BaseModel
import requests
from fastapi import Form
from fastapi.responses import StreamingResponse
import io




load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://74.248.111.249",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5500",   
        "http://127.0.0.1:5500"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

#blob storage setup
blob_service_client = BlobServiceClient.from_connection_string(connection_string)
container_name = "form-uploads"
container_client = blob_service_client.get_container_client(container_name)
if not container_client.exists():
    container_client.create_container()

#azure table storage setup for users
table_service_client = TableServiceClient.from_connection_string(connection_string)
table_client = table_service_client.get_table_client(table_name="users")
try:
    table_client.create_table()
except Exception:
    pass

#pydantic models for request bodies
class UserRegister(BaseModel):
    full_name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class StatusUpdate(BaseModel):
    status: str

@app.get("/")
def read_root():
    return {"message": "Backend is running successfully!"}

@app.post("/api/register")
def register_user(user: UserRegister):
    try:
        #password complexity
        password = user.password
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", password):
            raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", password):
            raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter.")
        if not re.search(r"\d", password):
            raise HTTPException(status_code=400, detail="Password must contain at least one number.")
        if not re.search(r"[!@#\$%\^&\*\(\)_\+\-=\[\]\{\};':\"\\|,.<>\/?/]", password):
            raise HTTPException(status_code=400, detail="Password must contain at least one special character (e.g., !@#$).")

        #user already exists?
        existing = list(table_client.query_entities(f"PartitionKey eq 'user' and RowKey eq '{user.email}'"))
        if len(existing) > 0:
            raise HTTPException(status_code=400, detail="User with this email already exists.")
        
        #hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        #create entity in azure table
        entity = {
            'PartitionKey': 'user',
            'RowKey': user.email,
            'full_name': user.full_name,
            'password_hash': hashed_password
        }
        table_client.create_entity(entity)
        return {"message": "User registered successfully!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/login")
def login_user(user: UserLogin):
    try:
        entities = list(table_client.query_entities(f"PartitionKey eq 'user' and RowKey eq '{user.email}'"))
        if len(entities) == 0:
            raise HTTPException(status_code=400, detail="Invalid email or password.")
        
        db_user = entities[0]
        #verify password hash
        valid = bcrypt.checkpw(user.password.encode('utf-8'), db_user['password_hash'].encode('utf-8'))
        if not valid:
            raise HTTPException(status_code=400, detail="Invalid email or password.")
            
        return {"message": "Login successful!", "full_name": db_user['full_name']}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
def upload_form(file: UploadFile = File(...), email: str = Form(...)):
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=file.filename)
        contents = file.file.read()
        blob_client.upload_blob(contents, overwrite=True)

        blob_client.set_blob_metadata(metadata={"status": "Pending", "department": "General"})

        #serverless logic app trigger
        logic_app_url = os.getenv("LOGIC_APP_URL")
        
        payload = {
            "email": email,           
            "filename": file.filename
        }
        
        try:
            requests.post(logic_app_url, json=payload)
            print(f"Logic App triggered for {email}")
        except Exception as e:
            print(f"Failed to trigger serverless email: {e}")


        return {"message": "File uploaded successfully!", "filename": file.filename}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents")
async def list_documents():
    try:
        blobs = container_client.list_blobs(include=['metadata'])
        docs = []
        for blob in blobs:
            meta = blob.metadata or {}
            docs.append({
                "name": blob.name,
                "size": round(blob.size / 1024, 2),
                "last_modified": blob.last_modified.strftime("%Y-%m-%d"),
                "status": meta.get("status", "Pending"),
                "department": meta.get("department", "General")
            })
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/documents/{filename}/status")
def update_status(filename: str, update: StatusUpdate):
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=filename)
        #fetch existing metadata
        blob_props = blob_client.get_blob_properties()
        meta = blob_props.metadata or {}
        
        #update the status
        meta["status"] = update.status
        blob_client.set_blob_metadata(metadata=meta)
        
        return {"message": "Status updated successfully in Azure!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents/{filename}/download")
async def download_document(filename: str):
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=filename)
        stream = blob_client.download_blob()
        data = stream.readall()
        return StreamingResponse(io.BytesIO(data), media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename={filename}"})
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.delete("/api/documents/{filename}")
async def delete_document(filename: str):
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=filename)
        blob_client.delete_blob()
        return {"message": f"Blob {filename} deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))