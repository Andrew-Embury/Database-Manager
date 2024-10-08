import os
import logging
import re
import emoji
from typing import List, Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime, timezone
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
import requests
import time
from dateutil import parser

# Set up logging
logging.basicConfig(level=logging.INFO)

class InstagramDataPipelineV2:
    def __init__(self):
        self.supabase = self.init_supabase()
        self.last_fetch_time = self.load_last_fetch_time()
        self.openai_client = self.init_openai()
        self.pinecone_index = self.init_pinecone()
        self.instagram_access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
        if not self.instagram_access_token:
            raise ValueError("INSTAGRAM_ACCESS_TOKEN not found in environment variables")
        self.base_url = "https://graph.instagram.com/v17.0"
        self.rate_limit_delay = 1  # 1 second delay between requests
        self.max_retries = 3

    def init_supabase(self) -> Client:
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL or SUPABASE_KEY not found in environment variables")
        return create_client(supabase_url, supabase_key)

    def init_openai(self) -> OpenAI:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        return OpenAI(api_key=openai_api_key)

    def init_pinecone(self):
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY not found in environment variables")
        pc = Pinecone(api_key=pinecone_api_key)
        
        index_name = "instagram-data"
        if index_name not in pc.list_indexes().names():
            pc.create_index(
                name=index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
        return pc.Index(index_name)

    def load_last_fetch_time(self) -> datetime:
        result = self.supabase.table('metadata').select('value').eq('key', 'last_fetch_time').execute()
        if result.data and isinstance(result.data[0].get('value'), str):
            return datetime.fromisoformat(result.data[0]['value']).replace(tzinfo=timezone.utc)
        return datetime.min.replace(tzinfo=timezone.utc)

    def save_last_fetch_time(self):
        self.supabase.table('metadata').upsert({'key': 'last_fetch_time', 'value': datetime.now(timezone.utc).isoformat()}).execute()

    def _make_paginated_request(self, url: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        all_data = []
        retry_count = 0

        while url and retry_count < self.max_retries:
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                all_data.extend(data.get('data', []))
                
                paging = data.get('paging', {})
                url = paging.get('next')  # Get the next URL for pagination
                
                if url:
                    params = {}  # Clear params for subsequent requests
                    time.sleep(self.rate_limit_delay)  # Respect rate limits
                
                retry_count = 0  # Reset retry count on successful request
            except requests.RequestException as e:
                retry_count += 1
                logging.warning(f"Request failed: {e}. Retrying ({retry_count}/{self.max_retries})...")
                time.sleep(self.rate_limit_delay * 2 ** retry_count)  # Exponential backoff

        if retry_count == self.max_retries:
            logging.error("Max retries reached. Some data may be missing.")

        return all_data

    def fetch_posts(self, limit: int = 100) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/me/media"
        params = {
            "fields": "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count",
            "access_token": self.instagram_access_token,
            "limit": limit
        }
        posts = self._make_paginated_request(url, params)
        new_posts = [
            post for post in posts 
            if parser.parse(post['timestamp']).replace(tzinfo=timezone.utc) > self.last_fetch_time
        ]
        return new_posts

    def fetch_comments(self, post_id: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/{post_id}/comments"
        params = {
            "fields": "id,text,timestamp,username",
            "access_token": self.instagram_access_token
        }
        comments = self._make_paginated_request(url, params)
        new_comments = [
            comment for comment in comments
            if parser.parse(comment['timestamp']).replace(tzinfo=timezone.utc) > self.last_fetch_time
        ]
        return new_comments

    def clean_text(self, text: str) -> str:
        if text is None:
            return ""
        text = emoji.demojize(text, language='en')
        text = text.lower()
        text = re.sub(r'http\S+|www.\S+', '', text)
        text = re.sub(r'[^a-zA-Z_:\s]', '', text)
        return ' '.join(text.split())

    def generate_embedding(self, text: str) -> List[float]:
        response = self.openai_client.embeddings.create(input=text, model="text-embedding-3-small")
        return response.data[0].embedding

    def process_and_upload_data(self):
        new_posts = self.fetch_posts()
        logging.info(f"Fetched {len(new_posts)} new posts")

        vectors = []

        for post in new_posts:
            clean_caption = self.clean_text(post.get('caption'))
            vector = {
                'id': post['id'],
                'values': self.generate_embedding(clean_caption),
                'metadata': {
                    'type': 'post',
                    'timestamp': post['timestamp'],
                    'likes': post.get('like_count', 0),  # Flatten engagement
                    'comments': post.get('comments_count', 0),  # Flatten engagement
                    'text': clean_caption  # Add the text field here
                }
            }
            vectors.append(vector)

            # Save post to Supabase
            self.supabase.table('posts').upsert(post, on_conflict='id').execute()

            # Fetch and process comments for this post
            comments = self.fetch_comments(post['id'])
            logging.info(f"Fetched {len(comments)} new comments for post {post['id']}")

            for comment in comments:
                clean_text = self.clean_text(comment.get('text'))
                vector = {
                    'id': comment['id'],
                    'values': self.generate_embedding(clean_text),
                    'metadata': {
                        'type': 'comment',
                        'timestamp': comment['timestamp'],
                        'post_id': post['id'],
                        'username': comment.get('username', 'unknown_user'),
                        'text': clean_text  # Add the text field here
                    }
                }
                vectors.append(vector)

                # Save comment to Supabase with "replied" field set to False
                comment['post_id'] = post['id']
                comment['replied'] = False  # Set default value for "replied"
                self.supabase.table('comments').upsert(comment, on_conflict='id').execute()

            time.sleep(self.rate_limit_delay)

        if vectors:
            self.pinecone_index.upsert(vectors=vectors)
            logging.info(f"Uploaded {len(vectors)} new vectors to Pinecone")
        else:
            logging.info("No new data to process and upload")

    def run(self):
        try:
            self.process_and_upload_data()
            self.save_last_fetch_time()
            logging.info("Data pipeline completed successfully")
        except Exception as e:
            logging.error(f"Error in data pipeline: {str(e)}")
            raise

def main(event, context):
    """
    Entry point for Google Cloud Function.
    """
    try:
        # Load environment variables from Google Cloud Function environment
        load_dotenv()

        pipeline = InstagramDataPipelineV2()
        pipeline.run()
        return "Data pipeline completed successfully", 200
    except Exception as e:
        logging.error(f"Error in data pipeline: {str(e)}")
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    # This block is for local testing
    main(None, None)