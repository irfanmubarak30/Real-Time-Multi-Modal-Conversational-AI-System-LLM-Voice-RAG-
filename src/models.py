from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# WhatsApp Webhook Models
class WhatsAppProfile(BaseModel):
    name: Optional[str] = None

class WhatsAppContact(BaseModel):
    profile: Optional[WhatsAppProfile] = None
    wa_id: Optional[str] = None

class WhatsAppText(BaseModel):
    body: str

class WhatsAppAudio(BaseModel):
    id: str
    mime_type: Optional[str] = None

class WhatsAppButtonReply(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None

class WhatsAppListReply(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None

class WhatsAppInteractive(BaseModel):
    type: str
    button_reply: Optional[WhatsAppButtonReply] = None
    list_reply: Optional[WhatsAppListReply] = None

class WhatsAppMessage(BaseModel):
    id: str
    from_: str = Field(alias="from")
    timestamp: str
    type: str
    text: Optional[WhatsAppText] = None
    audio: Optional[WhatsAppAudio] = None
    interactive: Optional[WhatsAppInteractive] = None

class WhatsAppValue(BaseModel):
    messaging_product: str
    metadata: Dict[str, Any]
    contacts: Optional[List[WhatsAppContact]] = None
    messages: Optional[List[WhatsAppMessage]] = None

class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str

class WhatsAppEntry(BaseModel):
    id: str
    changes: List[WhatsAppChange]

class WhatsAppWebhookData(BaseModel):
    object: str
    entry: List[WhatsAppEntry]

# Response Models
class WebhookResponse(BaseModel):
    status: str
    message: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str = "2.0.0"
