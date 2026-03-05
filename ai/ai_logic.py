import os
import base64
import re
import logging
import random
import time
from io import BytesIO

import torch
import torch.nn.functional as F
from PIL import Image
from dotenv import load_dotenv

from transformers import CLIPProcessor, CLIPModel
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
from pgvector.django import L2Distance
from django.db import connection
from django.conf import settings

from .models import AsortieKnowledge, ChatMessage
import requests 
import json
import cloudinary.uploader

load_dotenv()
logger = logging.getLogger(__name__)

# --- PROFESSIONAL KEY MANAGER ---
class GroqKeyManager:
    """Manages API keys to bypass standard rate limits."""
    @staticmethod
    def get_keys() -> list:
        keys = [value for key, value in os.environ.items() if key.startswith('GROQ_KEY_') and value]
        if not keys:
            fallback = os.getenv("GROQ_API_KEY")
            return [fallback] if fallback else []
        return keys

# --- INITIALIZE CPU-FRIENDLY EMBEDDING ENGINES ---
try:
    embedding_engine = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
except Exception as e:
    logger.critical("Text Memory engine failed to load: %s", e)

try:
    clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
except Exception as e:
    logger.critical("Vision Vector engine failed to load: %s", e)


class AsortieBrain:
    def __init__(self):
        # We don't initialize a single LLM here anymore. 
        # We will dynamically initialize them per request to allow for key rotation.
        self.available_keys = GroqKeyManager.get_keys()
        if not self.available_keys:
            logger.critical("No Groq API keys found!")

    def _get_llm(self, key: str, is_vision: bool = False):
        """Dynamically spins up an LLM instance with a specific key."""
        if is_vision:
            return ChatGroq(
                model_name="meta-llama/llama-4-maverick-17b-128e-instruct", 
                groq_api_key=key, 
                temperature=0
            )
        return ChatGroq(
            model_name="openai/gpt-oss-120b", 
            groq_api_key=key, 
            temperature=0
        )

    def _get_cloudinary_url(self, path):
        if not path: return ""
        if path.startswith('http'): return path
        return f"https://res.cloudinary.com/dhfyolanv/{path}"

    def _get_image_vector(self, img: Image.Image) -> str:
        if img.mode != 'RGB': 
            img = img.convert('RGB')
        
        inputs = clip_processor(images=img, return_tensors="pt")
        with torch.no_grad():
            features = clip_model.get_image_features(**inputs)
            
            if hasattr(features, 'image_embeds'):
                tensor = features.image_embeds
            elif hasattr(features, 'pooler_output'):
                tensor = features.pooler_output
            elif isinstance(features, tuple):
                tensor = features[0]
            else:
                tensor = features 

            image_vector = F.normalize(tensor, p=2, dim=-1)
            vector_list = image_vector.squeeze().tolist()
            return f"[{','.join(map(str, vector_list))}]"
        
    def search_knowledge(self, query: str) -> str:
        if not query or len(query) < 2: 
            return "Asortie Furniture: Founded in 1965. Specializes in luxury classical furniture."
        try:
            vector = embedding_engine.embed_query(query)
            facts = AsortieKnowledge.objects.order_by(L2Distance('embedding', vector))[:3]
            return "\n".join([f.content for f in facts])
        except Exception as e:
            logger.error("Knowledge Search Error: %s", e)
            return ""

    def _prepare_image(self, image_file) -> str:
        """Optimizes images for Vision LLM - CRITICAL FIX FOR 413 ERROR"""
        if hasattr(image_file, 'seek'): 
            image_file.seek(0)
        
        img = Image.open(image_file)
        if img.mode != 'RGB': 
            img = img.convert('RGB')
            
        # FIX: Reduced from 1024 to 400. This dramatically reduces the Base64 token payload
        # to fit safely under the 6,000 token limit.
        img.thumbnail((400, 400)) 
        buffered = BytesIO()
        
        # FIX: Reduced quality from 85 to 65 to further shrink the byte size
        img.save(buffered, format="JPEG", quality=65)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def search_image_database(self, image_file=None, limit=3, precomputed_vector=None) -> list:
        """
        Searches the database using pgvector. 
        Supports both raw image files and precomputed vector strings for speed.
        """
        try:
            vector_str = precomputed_vector
            
            # If no vector is provided, calculate it from the file
            if not vector_str and image_file:
                if hasattr(image_file, 'seek'):
                    image_file.seek(0)
                img = Image.open(image_file)
                vector_str = self._get_image_vector(img)
            
            if not vector_str:
                return []

            # Using Cosine Distance (<=>) for CLIP vectors.
            # Professional Thresholds: < 0.05 (Exact), < 0.25 (Very Similar)
            sql_search = """
                SELECT id, name, category, price, image, description, 
                       (image_embedding <=> %s::vector) as distance
                FROM market_product
                WHERE image_embedding IS NOT NULL
                ORDER BY distance ASC
                LIMIT %s;
            """
            
            with connection.cursor() as cursor:
                cursor.execute(sql_search, [vector_str, limit])
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                results = [dict(zip(columns, row)) for row in rows]
            
            # Format results for the Concierge
            for item in results:
                item['image'] = self._get_cloudinary_url(item['image'])
                # Convert distance to float for easier JSON handling
                if 'distance' in item:
                    item['distance'] = float(item['distance'])
                
            return results
            
        except Exception as e:
            logger.error("Visual Database Search Error: %s", e)
            return []
        
    def query_business_data(self, user_query: str, user_id: int = None) -> list:
        # We inject the specific user_id into the schema context for the SQL generator
        schema_context = f"""
        Current User ID: {user_id}
        Tables & Relationships:
        1. market_product (id, name, category, price, image, description, is_active, created_at, seller_id)
        Note: price=0 means 'price on request/negotiable'. price > 0 is 'starting price'.
        2. market_businessprofile (id, is_farmer, is_roaster, is_exporter, is_supplier, company_name, logo, country, city, description, core_products, user_id)
        3. market_order (id, status, quantity, total_price, created_at, buyer_id, product_id, seller_note)
           -> Relationship: market_order.product_id = market_product.id
        
        Business Logic for Smart Queries:
        - "My Favorites" or "I love": SELECT p.name, p.image, COUNT(o.id) as order_count 
          FROM market_product p JOIN market_order o ON p.id = o.product_id 
          WHERE o.buyer_id = {user_id} GROUP BY p.id, p.name, p.image ORDER BY order_count DESC;
          
        - "Global Favorites" or "Users love": SELECT p.name, p.image, COUNT(o.id) as total_sales 
          FROM market_product p JOIN market_order o ON p.id = o.product_id 
          GROUP BY p.id, p.name, p.image ORDER BY total_sales DESC;
        """
        
        sql_gen_prompt = f"""
        System: You are a PostgreSQL Expert. Convert the user request into a valid PostgreSQL SELECT query.
        
        Schema: {schema_context}
        STRICT RULES:
        1. Return ONLY the raw SQL code. No explanation. No backticks.
        2. Use the Current User ID ({user_id}) if the user asks about their own history or favorites.
        3. ALWAYS join market_product to get the 'name' and 'image' columns.
        4. Limit results to top 5.
        
        Request: {user_query}
        """
        
        try:
            llm = self._get_llm(random.choice(self.available_keys))
            sql_response = llm.invoke(sql_gen_prompt).content.strip()
            sql_query = re.sub(r'```sql|```', '', sql_response).strip()
            
            with connection.cursor() as cursor:
                cursor.execute(sql_query)
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                results = [dict(zip(columns, row)) for row in rows]
                
                for item in results:
                    if 'image' in item:
                        item['image'] = self._get_cloudinary_url(item['image'])
                return results
        except Exception as e:
            logger.error("SQL Execution Error: %s", e)
            return []
        
    def _execute_with_retry(self, messages, is_vision=False) -> str:
        """Professional Retry Logic: Tries different keys if one fails or hits a rate limit."""
        random.shuffle(self.available_keys) # Randomize order to balance load
        
        for attempt, key in enumerate(self.available_keys):
            try:
                llm = self._get_llm(key, is_vision)
                response = llm.invoke(messages)
                return response.content
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Key {attempt + 1} failed: {error_msg}")
                
                # If it's a hard token limit (413), retrying won't help. Break immediately.
                if "413" in error_msg or "too large" in error_msg.lower():
                    logger.error("Payload too large even after compression. Aborting retries.")
                    raise e 
                
                # If we have keys left, wait 1 second and try the next key
                if attempt < len(self.available_keys) - 1:
                    time.sleep(1)
                    continue
                else:
                    raise e # Exhausted all keys

    def ask(self, query: str, session_obj, image_file=None) -> dict:
        user = session_obj.user
        username = user.username
        user_role = user.role 
        user_tier = user.package_tier 
        facts = self.search_knowledge(query)
        
        # --- NEW: INTENT DETECTION ---
        query_lower = query.lower() if query else ""
        # Checks if user is asking for any kind of visual asset
        visual_intent = any(word in query_lower for word in ['image', 'picture', 'photo', 'jpg', 'png', 'logo', 'show me', 'branding'])
        
        data_snapshot = ""
        trigger_words = ['price', 'stock', 'order', 'market', 'sell', 'available', 'product', 'buy', 'image', 'show']
        
        if query and any(word in query_lower for word in trigger_words):
            raw_data = self.query_business_data(query, user_id=user.id)
            if raw_data:
                data_snapshot = f"\n[VERIFIED INVENTORY DATA]: {raw_data}"
            else:
                alternatives = self.query_business_data("Show me 3 available luxury items")
                data_snapshot = (
                    f"\n[SYSTEM NOTICE]: The specific item '{query}' was not found. "
                    f"ONLY suggest these REAL alternatives from the database: {alternatives}"
                )

        # --- NEW: SEARCH KNOWLEDGE ASSETS BY TEXT ---
        # If user asks for an image, we specifically search the Knowledge table for a matching image URL
        knowledge_asset_context = ""
        if visual_intent:
            # Clean the query to get the core keyword (e.g., "your logo" -> "logo")
            search_keyword = query_lower.replace("show me", "").replace("your", "").replace("the", "").strip()
            
            # Look for knowledge rows that have a Cloudinary URL 
            # and where the content contains our keyword (e.g., "logo")
            asset_match = AsortieKnowledge.objects.filter(
                knowledge_image__isnull=False
            ).filter(content__icontains=search_keyword).first()
            
            if asset_match:
                img_md = f"![{asset_match.content}]({asset_match.knowledge_image})"
                # We use a very strong SYSTEM NOTICE to override the AI's "I don't have it" excuse
                knowledge_asset_context = (
                    f"\n[SYSTEM NOTICE - MANDATORY IMAGE DISPLAY]: "
                    f"The user requested an asset. Found: {asset_match.content}. "
                    f"The image URL IS available: {asset_match.knowledge_image}. "
                    f"You MUST show this image now: {img_md}"
                )

        visual_match_context = "\n[SYSTEM NOTICE]: No visual match requested or found."

        if image_file:
            # Reset pointer to ensure we read from the start
            if hasattr(image_file, 'seek'): image_file.seek(0)
            img = Image.open(image_file)
            
            # 1. Get the vector as a STRING (e.g., "[0.12, -0.04...]")
            img_vector_str = self._get_image_vector(img)
            
            # 2. FIX: Convert the string to a LIST of floats for the Django ORM
            img_vector_list = json.loads(img_vector_str)
            
            # --- STEP 1: CHECK FOR TRAINED ASSETS (Logo, Office, etc.) ---
            trained_asset = AsortieKnowledge.objects.filter(image_embedding__isnull=False).annotate(
                distance=L2Distance('image_embedding', img_vector_list)
            ).order_by('distance').first()

            # --- STEP 2: CHECK FOR MARKET PRODUCTS ---
            visual_results = self.search_image_database(precomputed_vector=img_vector_str)
            
            # --- STEP 3: LOGIC PRIORITY ---
            if trained_asset and float(trained_asset.distance) < 0.05:
                img_md = f"\n![{trained_asset.content}]({trained_asset.knowledge_image})" if trained_asset.knowledge_image else ""
                visual_match_context = (
                    f"\n[SYSTEM NOTICE - BRAND IDENTITY MATCH]: This is exactly {trained_asset.content}. "
                    f"Respond as a concierge and display this image: {img_md}"
                )
            
            elif visual_results and visual_results[0].get('distance', 1.0) < 0.05:
                best_match = visual_results[0]
                visual_match_context = (
                    f"\n[SYSTEM NOTICE - EXACT PRODUCT MATCH]: This is an exact item from our inventory. "
                    f"Product Details: {best_match}. You MUST provide specific details about this item."
                )
            
            elif visual_results and visual_results[0].get('distance', 1.0) < 0.30:
                visual_match_context = (
                    f"\n[SYSTEM NOTICE - SIMILAR ITEMS]: We don't have the exact piece, but we have these similar luxury items: "
                    f"{visual_results}. Suggest these to the client as bespoke alternatives."
                )
            
            else:
                visual_match_context = "\n[SYSTEM NOTICE]: No visual match in database. Perform general aesthetic analysis of the furniture/space."

            if hasattr(image_file, 'seek'):
                image_file.seek(0)

        pricing_philosophy = (
            "LUXURY PRICING RULES:\n"
            "1. If a product price is 0, DO NOT say it is free. Tell the client: 'The actual price for this piece is determined via private negotiation per order.'\n"
            "2. If a price is greater than 0, refer to it ONLY as a 'Starting Price' or 'Base Price'.\n"
            "3. Explicitly state that as a luxury brand, we do not have fixed prices because market costs for premium materials fluctuate daily.\n"
            "4. All pricing mentioned is an estimate subject to final bespoke specifications and current market rates."
        )

        system_identity = (
            "IDENTITY: You are the Asortie Super Intelligence, a concierge for a world-class luxury furniture house. "
            f"{pricing_philosophy}\n"
            "CRITICAL CONSTRAINT: You are FORBIDDEN from inventing or hallucinating product names. "
            "Only discuss products explicitly listed in the [VERIFIED INVENTORY DATA] below. "
            "If the client asks for alternatives, you MUST query the database for existing products. "
            "instead of creating fictional pieces like 'Regal Mahogany' or 'Sovereign Velvet'. "
            "If no data is provided in the snapshot, state clearly that no items match the criteria."
            "STRICT RULE: You only talk about products found in the [VERIFIED INVENTORY DATA] or [VISUAL MATCH]. "
            "If the data snapshot says an item is NOT in the database, you MUST inform the client "
            "that we do not currently have that specific piece in our digital assets, "
            "but offer to search for a similar bespoke alternative."
            "You have direct, real-time access to the Product, Market, and Order tables. "
            "IMPORTANT: Use the 'VERIFIED DATABASE DATA' provided below. "
            "IMAGE RULE: If the data contains an 'image', you MUST display it using exactly the URL provided. "
            "Format: ![Name](URL_HERE). Do NOT add '/media/' to the URL."
            "CONCIERGE DATA ANALYSIS RULES:\n"
            "1. If you see 'order_count' in the [VERIFIED INVENTORY DATA], it means these are the user's personal favorites. Mention their 'exquisite recurring taste'.\n"
            "2. If you see 'total_sales', these are the most popular items globally. Refer to them as 'Our most coveted pieces among the global elite'.\n"
            "3. If an image URL is present, you MUST display it: ![Product Name](URL).\n"
            f"\n[VERIFIED INVENTORY DATA]: {data_snapshot}\n"
            f"{knowledge_asset_context}\n" # Injecting text-based image search results
            f"{visual_match_context}\n"
            f"CLIENT INFO: User '{username}' is a '{user_role}' with a '{user_tier}' membership. "
            f"TONE: {'Extremely priority/concierge' if user_tier == 'professional' else 'Sophisticated'}. "
            f"SYSTEM KNOWLEDGE: {facts}"
        )

        try:
            db_history = ChatMessage.objects.filter(session=session_obj).order_by('-timestamp')[:10]

            if image_file:
                encoded_image = self._prepare_image(image_file)
                messages = [HumanMessage(content=[
                    {
                        "type": "text", 
                        "text": f"{system_identity}\n\nClient Request: {query or 'Analyze this piece.'}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encoded_image}"
                        }
                    },
                ])]
                answer = self._execute_with_retry(messages, is_vision=True)
            else:
                messages = [SystemMessage(content=system_identity)]
                for h in reversed(db_history):
                    role_label = "Client" if h.role == 'user' else "Concierge"
                    messages.append(HumanMessage(content=f"{role_label}: {h.message}"))
                
                messages.append(HumanMessage(content=query or "[Empty Query]"))
                answer = self._execute_with_retry(messages, is_vision=False)

            # Save Transaction
            user_msg = ChatMessage.objects.create(
                session=session_obj, role='user', 
                message=query or "[Visual Analysis Request]", image=image_file
            )
            ChatMessage.objects.create(session=session_obj, role='assistant', message=answer)

            if session_obj.title == "New Luxury Inquiry" and query:
                session_obj.title = query[:30].strip() + "..."
                session_obj.save()

            return {"answer": answer, "user_msg_id": user_msg.id}

        except Exception as e:
            logger.error("AI ENGINE ERROR: %s", e)
            return {"answer": "Our luxury data hub is experiencing high demand. Please try your request again in a moment.", "user_msg_id": None}
        
    def teach(self, text: str) -> bool:
        try:
            vector = embedding_engine.embed_query(text)
            AsortieKnowledge.objects.create(content=text, embedding=vector)
            logger.info("Successfully trained AI on: %s...", text[:30])
            return True
        except Exception as e:
            logger.error("TEACH ERROR: %s", e)
            raise e
        
    def teach_image_vectors(self):
            logger.info("Starting Visual Vectorization for existing products...")
            cloud_name = "dhfyolanv" 
            sql_fetch = "SELECT id, image FROM market_product WHERE image_embedding IS NULL AND image IS NOT NULL;"
            
            with connection.cursor() as cursor:
                cursor.execute(sql_fetch)
                products = cursor.fetchall()
                
                for prod_id, img_path in products:
                    try:
                        if not str(img_path).startswith('http'):
                            full_url = f"https://res.cloudinary.com/{cloud_name}/{img_path}"
                        else:
                            full_url = img_path
                            
                        response = requests.get(full_url, timeout=15)
                        response.raise_for_status() 
                        
                        img = Image.open(BytesIO(response.content))
                        vector_str = self._get_image_vector(img)
                        
                        update_sql = "UPDATE market_product SET image_embedding = %s::vector WHERE id = %s;"
                        cursor.execute(update_sql, [vector_str, prod_id])
                        logger.info("Successfully vectorized Product ID %s", prod_id)
                        
                    except Exception as e:
                        logger.error("Failed to vectorize Product ID %s: %s", prod_id, e)
                        
            logger.info("Vectorization complete.")
            
    # --- ADD THESE TO AsortieBrain IN ai_logic.py ---

    def edit_knowledge(self, knowledge_id: int, new_text: str) -> bool:
        """Re-embeds and updates an existing fact."""
        try:
            # Re-generate the vector for the new text
            new_vector = embedding_engine.embed_query(new_text)
            
            # Update the database
            fact = AsortieKnowledge.objects.get(id=knowledge_id)
            fact.content = new_text
            fact.embedding = new_vector
            fact.save()
            logger.info(f"Knowledge {knowledge_id} updated successfully.")
            return True
        except Exception as e:
            logger.error("EDIT ERROR: %s", e)
            return False

    def delete_knowledge(self, knowledge_id: int) -> bool:
        """Permanently removes a fact from AI memory."""
        try:
            AsortieKnowledge.objects.filter(id=knowledge_id).delete()
            logger.info(f"Knowledge {knowledge_id} deleted successfully.")
            return True
        except Exception as e:
            logger.error("DELETE ERROR: %s", e)
            return False

    def teach_visual_asset(self, image_file, label: str) -> bool:
        try:
            # 1. Upload to Cloudinary for UI display
            if hasattr(image_file, 'seek'): image_file.seek(0)
            upload_result = cloudinary.uploader.upload(image_file, folder="asortie_ai_assets/")
            cloudinary_url = upload_result.get('secure_url')
            
            # 2. Vectorize for AI Recognition
            image_file.seek(0)
            img = Image.open(image_file)
            vector_str = self._get_image_vector(img)
            vector_list = json.loads(vector_str)

            # 3. Save to Knowledge Base
            from ai.models import AsortieKnowledge
            AsortieKnowledge.objects.create(
                content=f"Identified Brand Asset: {label}",
                image_embedding=vector_list,
                knowledge_image=cloudinary_url # This links the image to the UI
            )
            return True
        except Exception as e:
            logger.error(f"Visual training error: {e}")
            return False