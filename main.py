from fastapi import FastAPI, WebSocket, File, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List
import os
from fastapi import Depends
from sqlalchemy.orm import Session
import uvicorn

from database import Chatroom,Users,Message, SessionLocal, engine

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Serve static files (optional, only for the example frontend)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates (optional, only for the example frontend)

# Dictionary to store chatrooms and their messages
chatrooms = {}

@app.websocket("/ws/{chatroom_id}/{user}")
async def websocket_endpoint(websocket: WebSocket, chatroom_id: str, user: str):
    await websocket.accept()

    # Join the chatroom
    if chatroom_id not in chatrooms:
        chatrooms[chatroom_id] = {"participants": set(), "messages": []}

    chatrooms[chatroom_id]["participants"].add(websocket)

    try:
        while True:
            data = await websocket.receive_text()

            # Handle different message types (text or attachment)
            if data.startswith("TEXT:"):
                # Extract text message
                text_message = data[len("TEXT:"):]
                message = {"type": "text", "user": user, "content": text_message}
            elif data.startswith("ATTACHMENT:"):
                # Extract attachment filename
                attachment_filename = data[len("ATTACHMENT:"):]

                # Save the attachment to the appropriate directory
                attachment_path = f"root/{attachment_filename}"
                with open(attachment_path, "wb") as attachment_file:
                    attachment_data = await websocket.receive_bytes()
                    attachment_file.write(attachment_data)

                message = {"type": "attachment", "user": user, "content": attachment_filename, "path": attachment_path}
            else:
                continue

            # Add the message to the chatroom's message history
            chatrooms[chatroom_id]["messages"].append(message)

            # Broadcast the message to all participants in the chatroom
            for participant in chatrooms[chatroom_id]["participants"]:
                if message["type"] == "text":
                    await participant.send_text(f"{user}: {text_message}")
                elif message["type"] == "attachment":
                    await participant.send_text(f"{user} sent an attachment: {attachment_filename}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Remove the participant from the chatroom upon leaving
        chatrooms[chatroom_id]["participants"].remove(websocket)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: List[str] = []):
    return {"message": "Attachment sent successfully"}

@app.get("/chatrooms", response_model=List[str])
async def list_chatrooms(db: Session = Depends(get_db)):
    chatrooms = db.query(Chatroom.id).all()  # Assuming 'id' is the field that stores chatroom's identifier
    chatroom_ids = [chatroom.id for chatroom in chatrooms]
    return chatroom_ids


@app.post("/create_user/{name}")
async def create_user(name: str, db: Session = Depends(get_db)):
    db_user = Users(username=name)
    db.add(db_user)
    db.commit()
    return {"message": f"User {name} created successfully!"}

@app.post("/create_chatroom/{chatroom_id}")
async def create_chatroom(chatroom_id: str, db: Session = Depends(get_db)):
    db_chatroom = Chatroom(id=chatroom_id)
    db.add(db_chatroom)
    db.commit()
    chatrooms[chatroom_id] = {"participants": set(), "messages": []}
    return {"message": f"Chatroom {chatroom_id} created successfully!"}

@app.post("/enter_chatroom/{chatroom_id}/{user}")
async def enter_chatroom(chatroom_id: str, user: str, db: Session = Depends(get_db)):
    # Check if the chatroom exists in the database
    db_chatroom = db.query(Chatroom).filter(Chatroom.id == chatroom_id).first()
    if not db_chatroom:
        return {"error": "Chatroom not found"}

    # Optionally, check if the user exists in the database
    db_user = db.query(Users).filter(Users.username == user).first()
    if not db_user:
        return {"error": "User not found"}

    # Add user to the in-memory chatroom participants (if not already added)
    if chatroom_id not in chatrooms:
        chatrooms[chatroom_id] = {"participants": set(), "messages": []}
    chatrooms[chatroom_id]["participants"].add(user)
    
    return {"message": f"{user} entered the chatroom {chatroom_id}"}


@app.post("/send_message/{chatroom_id}/{user}")
async def send_message(chatroom_id: str, user: str, message: str, db: Session = Depends(get_db)):
    db_chatroom = db.query(Chatroom).filter(Chatroom.id == chatroom_id).first()
    if not db_chatroom:
        return {"error": "Chatroom not found"}
    db_user = db.query(Users).filter(Users.username == user).first()
    if not db_user:
        return {"error": "User not found"}
    new_message = Message(content=message, type="text", user=user, chatroom_id=chatroom_id)
    db.add(new_message)
    db.commit()
    if chatroom_id in chatrooms:
        # Broadcast the message to all participants in the chatroom
        for participant in chatrooms[chatroom_id]["participants"]:
            if isinstance(participant, WebSocket):
                await participant.send_text(f"{user}: {message}")
            else:
                print(f"Invalid participant in chatroom {chatroom_id}: {participant}")
        return {"message": "Text message sent successfully"}
    else:
        return {"error": "Chatroom not found in memory"}

# Start up event to initialize chatrooms from DB



@app.post("/send_attachment/{chatroom_id}/{user}")
async def send_attachment(chatroom_id: str, user: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Check if the chatroom exists in the database
    db_chatroom = db.query(Chatroom).filter(Chatroom.id == chatroom_id).first()
    if not db_chatroom:
        return {"error": "Chatroom not found"}

    # Ensure the 'root' directory exists
    root_directory = "root"
    if not os.path.exists(root_directory):
        os.makedirs(root_directory)

    # Construct the file path
    attachment_path = os.path.join(root_directory, file.filename)

    # Save the attachment to the appropriate directory
    with open(attachment_path, "wb") as attachment_file:
        attachment_data = await file.read()
        attachment_file.write(attachment_data)

    # Create and add the attachment message to the database
    new_message = Message(content=file.filename, type="attachment", user=user, chatroom_id=chatroom_id)
    db.add(new_message)
    db.commit()

    # Optionally, add the attachment message to the chatroom's message history in memory
    if chatroom_id in chatrooms:
        chatrooms[chatroom_id]["messages"].append({
            "type": "attachment",
            "user": user,
            "content": file.filename,
            "path": attachment_path
        })

        # Broadcast the attachment message to all participants in the chatroom
        for participant in chatrooms[chatroom_id]["participants"]:
            if isinstance(participant, WebSocket):
                await participant.send_text(f"{user} sent an attachment: {file.filename}")
            else:
                print(f"Invalid participant in chatroom {chatroom_id}: {participant}")

        return {"message": "Attachment sent successfully"}
    else:
        return {"error": "Chatroom not found in memory"}


@app.get("/list_messages/{chatroom_id}", response_model=List[dict])
async def list_messages(chatroom_id: str, db: Session = Depends(get_db)):
    # Check if the chatroom exists
    db_chatroom = db.query(Chatroom).filter(Chatroom.id == chatroom_id).first()
    if not db_chatroom:
        return {"error": "Chatroom not found"}

    # Query messages for the chatroom
    db_messages = db.query(Message).filter(Message.chatroom_id == chatroom_id).all()

    # Convert messages to a list of dictionaries
    messages_list = [{"id": message.id, "content": message.content, "type": message.type, "user": message.user} for message in db_messages]
    
    return messages_list

@app.get("/download_attachment/{chatroom_id}/{attachment_filename}")
async def download_attachment(chatroom_id: str, attachment_filename: str):
    attachment_path = f"root/{attachment_filename}"
    if os.path.exists(attachment_path):
        return FileResponse(attachment_path, media_type="application/octet-stream", filename=attachment_filename)
    else:
        return {"error": "Attachment not found"}




@app.on_event("startup")
async def startup_event():
    db = SessionLocal()
    db_chatrooms = db.query(Chatroom).all()
    for chatroom in db_chatrooms:
        chatrooms[chatroom.id] = {"participants": set(), "messages": []}
    db.close()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)