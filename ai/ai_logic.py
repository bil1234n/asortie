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

# Django & Third Party
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from pgvector.django import L2Distance
from django.db import connection
from django.conf import settings
import cloudinary.uploader

from .models import AsortieKnowledge, ChatMessage

load_dotenv()
logger = logging.getLogger(__name__)

class AsortieBrain:
    def __init__(self):
        self.available_keys = [v for k, v in os.environ.items() if k.startswith('GROQ_KEY_') and v]
        self.hf_token = os.environ.get("HUGGINGFACE_API_KEY")
        # Hugging Face API URLs
        self.clip_api = "https://api-inference.huggingface.co/models/openai/clip-vit-base-patch32"
        self.text_api = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
        self.headers = {"Authorization": f"Bearer {self.hf_token}"}

    def _get_llm(self, key: str, is_vision: bool = False):
        model = "meta-llama/llama-3.2-11b-vision-preview" if is_vision else "llama3-70b-8192"
        return ChatGroq(model_name=model, groq_api_key=key, temperature=0)

    # --- NEW: API BASED EMBEDDINGS (Replaces Torch) ---
    def _get_hf_embedding(self, api_url, payload, is_image=False):
        """Calls Hugging Face API with retry logic for model loading."""
        for _ in range(3):
            if is_image:
                response = requests.post(api_url, headers=self.headers, data=payload)
            else:
                response = requests.post(api_url, headers=self.headers, json=payload)
            
            result = response.json()
            if isinstance(result, dict) and "estimated_time" in result:
                time.sleep(result["estimated_time"]) # Wait if model is starting
                continue
            return result
        return None

    def _get_image_vector(self, img: Image.Image) -> str:
        """Gets vector from Hugging Face API instead of local Torch."""
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        vector = self._get_hf_embedding(self.clip_api, buffered.getvalue(), is_image=True)
        # CLIP API returns a list of floats
        return f"[{','.join(map(str, vector))}]"

    def search_knowledge(self, query: str) -> str:
        try:
            vector = self._get_hf_embedding(self.text_api, {"inputs": query})
            facts = AsortieKnowledge.objects.order_by(L2Distance('embedding', vector))[:3]
            return "\n".join([f.content for f in facts])
        except Exception as e:
            return "Asortie Furniture: Luxury classical furniture experts."

    # --- CLOUDINARY & IMAGE HELPERS ---
    def _get_cloudinary_url(self, path):
        if not path: return ""
        if str(path).startswith('http'): return path
        return f"https://res.cloudinary.com/dhfyolanv/{path}"

    def _prepare_image(self, image_file) -> str:
        img = Image.open(image_file)
        img.thumbnail((400, 400)) 
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=65)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def search_image_database(self, image_file=None, limit=3, precomputed_vector=None) -> list:
        try:
            vector_str = precomputed_vector
            if not vector_str and image_file:
                image_file.seek(0)
                vector_str = self._get_image_vector(Image.open(image_file))
            
            sql_search = """
                SELECT id, name, category, price, image, description, 
                       (image_embedding <=> %s::vector) as distance
                FROM market_product WHERE image_embedding IS NOT NULL
                ORDER BY distance ASC LIMIT %s;
            """
            with connection.cursor() as cursor:
                cursor.execute(sql_search, [vector_str, limit])
                columns = [col[0] for col in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            for item in results:
                item['image'] = self._get_cloudinary_url(item['image'])
            return results
        except Exception:
            return []

    # --- THE CONCIERGE "ASK" LOGIC ---
    def ask(self, query: str, session_obj, image_file=None) -> dict:
        user = session_obj.user
        facts = self.search_knowledge(query) if query else ""
        
        visual_match_context = ""
        if image_file:
            image_file.seek(0)
            img_vector_str = self._get_image_vector(Image.open(image_file))
            visual_results = self.search_image_database(precomputed_vector=img_vector_str)
            
            if visual_results and float(visual_results[0].get('distance', 1.0)) < 0.25:
                visual_match_context = f"\n[VISUAL MATCH]: Found similar item: {visual_results[0]}"
            else:
                visual_match_context = "\n[SYSTEM]: No specific product match found."

        system_identity = (
            f"You are the Asortie Luxury Concierge. \n"
            f"KNOWLEDGE: {facts}\n"
            f"{visual_match_context}\n"
            f"Tone: Elegant and Sophisticated."
        )

        try:
            if image_file:
                encoded = self._prepare_image(image_file)
                messages = [HumanMessage(content=[
                    {"type": "text", "text": f"{system_identity}\nQuery: {query or 'Analyze this.'}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}
                ])]
                answer = self._get_llm(random.choice(self.available_keys), True).invoke(messages).content
            else:
                messages = [SystemMessage(content=system_identity), HumanMessage(content=query)]
                answer = self._get_llm(random.choice(self.available_keys)).invoke(messages).content

            ChatMessage.objects.create(session=session_obj, role='user', message=query or "[Image]")
            ChatMessage.objects.create(session=session_obj, role='assistant', message=answer)
            return {"answer": answer}
        except Exception as e:
            logger.error(e)
            return {"answer": "Our system is busy. Please try again."}

    # --- TEACHING WITH CLOUDINARY ---
    def teach_visual_asset(self, image_file, label: str) -> bool:
        try:
            # 1. Upload to Cloudinary
            image_file.seek(0)
            upload = cloudinary.uploader.upload(image_file, folder="asortie_ai_assets/")
            
            # 2. Vectorize via API
            image_file.seek(0)
            vector_str = self._get_image_vector(Image.open(image_file))
            vector_list = json.loads(vector_str)

            # 3. Save
            AsortieKnowledge.objects.create(
                content=label,
                image_embedding=vector_list,
                knowledge_image=upload.get('secure_url')
            )
            return True
        except Exception as e:
            logger.error(e)
            return False
