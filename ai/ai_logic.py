import os
import base64
import re
import logging
import random
import time
import json
import requests
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

# Django & DB
from django.db import connection
from django.conf import settings
from pgvector.django import L2Distance

# AI & Third Party
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
import cloudinary.uploader

from .models import AsortieKnowledge, ChatMessage

load_dotenv()
logger = logging.getLogger(__name__)

class GroqKeyManager:
    @staticmethod
    def get_keys() -> list:
        keys = [v for k, v in os.environ.items() if k.startswith('GROQ_KEY_') and v]
        return keys if keys else [os.getenv("GROQ_API_KEY")]

class AsortieBrain:
    def __init__(self):
        self.available_keys = GroqKeyManager.get_keys()
        self.hf_token = os.environ.get("HUGGINGFACE_API_KEY")
        
        # Hugging Face API Endpoints
        self.clip_api_url = "https://api-inference.huggingface.co/models/openai/clip-vit-base-patch32"
        self.text_api_url = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
        self.headers = {"Authorization": f"Bearer {self.hf_token}"}

    def _get_llm(self, key: str, is_vision: bool = False):
        # Using the newest Llama 3.3 (70B) for high intelligence
        model_name = "llama-3.2-11b-vision-preview" if is_vision else "llama-3.3-70b-versatile"
        return ChatGroq(model_name=model_name, groq_api_key=key, temperature=0.1)

    def _get_hf_api_embedding(self, url, payload, is_image=False):
        """Fix: Handles Hugging Face responses correctly to avoid float() errors."""
        try:
            for _ in range(3):
                response = requests.post(url, headers=self.headers, data=payload if is_image else json.dumps(payload), timeout=20)
                result = response.json()
                
                if isinstance(result, dict) and "estimated_time" in result:
                    time.sleep(min(result["estimated_time"], 5))
                    continue
                
                # Ensure we return a flat list of floats
                if isinstance(result, list):
                    if len(result) > 0 and isinstance(result[0], list):
                        return result[0] # Handle nested list [[...]]
                    return result
            return None
        except Exception as e:
            logger.error(f"Embedding Error: {e}")
            return None

    def _get_cloudinary_url(self, path):
        if not path: return ""
        if str(path).startswith('http'): return path
        return f"https://res.cloudinary.com/dhfyolanv/{path}"

    def _get_image_vector(self, img: Image.Image) -> str:
        if img.mode != 'RGB': img = img.convert('RGB')
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        vector = self._get_hf_api_embedding(self.clip_api_url, buffered.getvalue(), is_image=True)
        return f"[{','.join(map(str, vector))}]" if vector else "[]"
        
    def search_knowledge(self, query: str) -> str:
        if not query or len(query) < 2: return ""
        vector = self._get_hf_api_embedding(self.text_api_url, {"inputs": query})
        if not vector or not isinstance(vector, list): return ""
        try:
            facts = AsortieKnowledge.objects.order_by(L2Distance('embedding', vector))[:3]
            return "\n".join([f.content for f in facts])
        except: return ""

    def query_business_data(self, user_query: str, user_id: int = None) -> list:
        schema = f"User ID: {user_id}. Tables: market_product(name, price, image), market_order(buyer_id, product_id)."
        prompt = f"System: SQL Expert. Return ONLY raw PostgreSQL SQL for: {user_query}. Schema: {schema}"
        try:
            llm = self._get_llm(random.choice(self.available_keys))
            sql = re.sub(r'```sql|```', '', llm.invoke(prompt).content).strip()
            with connection.cursor() as cursor:
                cursor.execute(sql)
                cols = [c[0] for c in cursor.description]
                res = [dict(zip(cols, r)) for r in cursor.fetchall()]
                for i in res: 
                    if 'image' in i: i['image'] = self._get_cloudinary_url(i['image'])
                return res
        except: return []

    def ask(self, query: str, session_obj, image_file=None) -> dict:
        user = session_obj.user
        facts = self.search_knowledge(query)
        
        # Data & Visual Logic
        data_snapshot = ""
        if query and any(w in query.lower() for w in ['price', 'product', 'buy', 'order']):
            raw = self.query_business_data(query, user_id=user.id)
            data_snapshot = f"\n[VERIFIED INVENTORY DATA]: {raw}"

        visual_match = ""
        if image_file:
            image_file.seek(0)
            vec = self._get_image_vector(Image.open(image_file))
            res = self.search_image_database(precomputed_vector=vec)
            if res: visual_match = f"\n[VISUAL MATCH]: {res[0]}"

        # RESTORED SMART PROMPT
        system_identity = (
            "IDENTITY: You are the Asortie Super Intelligence, a concierge for a luxury furniture house. "
            "PRICING RULES: Price 0 means 'Negotiation Required'. Price > 0 is 'Starting Price'. "
            "RULES: Never hallucinate products. Only use [VERIFIED INVENTORY DATA]. "
            "If an image URL is in the data, display it: ![Name](URL). "
            f"\nINVENTORY: {data_snapshot}\nVISUAL: {visual_match}\nKNOWLEDGE: {facts}\n"
            f"Client: {user.username} (Role: {user.role})"
        )

        try:
            llm = self._get_llm(random.choice(self.available_keys), is_vision=bool(image_file))
            if image_file:
                image_file.seek(0)
                img = Image.open(image_file)
                img.thumbnail((400, 400))
                buf = BytesIO()
                img.save(buf, format="JPEG")
                encoded = base64.b64encode(buf.getvalue()).decode('utf-8')
                
                msgs = [HumanMessage(content=[
                    {"type": "text", "text": system_identity},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}
                ])]
                answer = llm.invoke(msgs).content
            else:
                msgs = [SystemMessage(content=system_identity), HumanMessage(content=query or "Analyze.")]
                answer = llm.invoke(msgs).content

            user_msg = ChatMessage.objects.create(session=session_obj, role='user', message=query or "[Visual Inquiry]", image=image_file)
            ChatMessage.objects.create(session=session_obj, role='assistant', message=answer)
            return {"answer": answer, "user_msg_id": user_msg.id}
        except Exception as e:
            logger.error(f"AI ERROR: {e}")
            return {"answer": "I am momentarily unavailable. Please try again."}

    def search_image_database(self, image_file=None, limit=3, precomputed_vector=None) -> list:
        try:
            vec = precomputed_vector or self._get_image_vector(Image.open(image_file))
            if not vec or vec == "[]": return []
            sql = "SELECT name, price, image, (image_embedding <=> %s::vector) as dist FROM market_product ORDER BY dist ASC LIMIT %s;"
            with connection.cursor() as cursor:
                cursor.execute(sql, [vec, limit])
                cols = [c[0] for c in cursor.description]
                res = [dict(zip(cols, r)) for r in cursor.fetchall()]
                for i in res: i['image'] = self._get_cloudinary_url(i['image'])
            return res
        except: return []

    def teach_visual_asset(self, image_file, label: str) -> bool:
        try:
            image_file.seek(0)
            up = cloudinary.uploader.upload(image_file, folder="asortie_ai/")
            image_file.seek(0)
            vec = json.loads(self._get_image_vector(Image.open(image_file)))
            AsortieKnowledge.objects.create(content=label, image_embedding=vec, knowledge_image=up.get('secure_url'))
            return True
        except: return False
