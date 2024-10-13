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

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
                logger.debug(f"Making request to URL: {url}")
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                logger.debug(f"Received data: {data}")
                all_data.extend(data.get('data', []))
                
                paging = data.get('paging', {})
                url = paging.get('next')  # Get the next URL for pagination
                
                if url:
                    params = {}  # Clear params for subsequent requests
                    time.sleep(self.rate_limit_delay)  # Respect rate limits
                
                retry_count = 0  # Reset retry count on successful request
            except requests.RequestException as e:
                retry_count += 1
                logger.warning(f"Request failed: {e}. Retrying ({retry_count}/{self.max_retries})...")
                time.sleep(self.rate_limit_delay * 2 ** retry_count)  # Exponential backoff

        if retry_count == self.max_retries:
            logger.error("Max retries reached. Some data may be missing.")

        logger.debug(f"Total data fetched: {len(all_data)}")
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
            "fields": "id,text,timestamp,username,replies",
            "access_token": self.instagram_access_token
        }
        return self._make_paginated_request(url, params)

    def fetch_replies(self, comment_id: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/{comment_id}/replies"
        params = {
            "fields": "id,text,timestamp,username",
            "access_token": self.instagram_access_token
        }
        logger.debug(f"Fetching replies for comment {comment_id}")
        replies = self._make_paginated_request(url, params)
        logger.debug(f"Fetched {len(replies)} total replies for comment {comment_id}")
        new_replies = [
            reply for reply in replies
            if parser.parse(reply['timestamp']).replace(tzinfo=timezone.utc) > self.last_fetch_time
        ]
        logger.debug(f"Found {len(new_replies)} new replies for comment {comment_id}")
        return new_replies

    def clean_text(self, text: str) -> str:
        if text is None:
            return ""
        text = emoji.demojize(text, language='en')
        text = text.lower()
        text = re.sub(r'http\S+|www.\S+', '', text)
        text = re.sub(r'[^a-zA-Z_:\s]', '', text)
        text = re.sub(r':', '', text)  # Remove colons from emoji names
        return ' '.join(text.split())

    def generate_embedding(self, text: str) -> List[float]:
        response = self.openai_client.embeddings.create(input=text, model="text-embedding-3-small")
        return response.data[0].embedding

    def process_and_upload_data(self):
        all_posts = self.fetch_all_posts()
        logger.info(f"Fetched {len(all_posts)} posts")

        vectors = []

        for post in all_posts:
            try:
                post_timestamp = parser.parse(post['timestamp']).replace(tzinfo=timezone.utc)
                
                if post_timestamp > self.last_fetch_time:
                    # Process new post
                    clean_caption = self.clean_text(post.get('caption'))
                    vector = {
                        'id': post['id'],
                        'values': self.generate_embedding(clean_caption),
                        'metadata': {
                            'type': 'post',
                            'timestamp': post['timestamp'],
                            'likes': post.get('like_count', 0),
                            'comments': post.get('comments_count', 0),
                            'text': clean_caption
                        }
                    }
                    vectors.append(vector)
                    self.supabase.table('posts').upsert(post, on_conflict='id').execute()

                comments = self.fetch_comments(post['id'])
                logger.info(f"Fetched {len(comments)} comments for post {post['id']}")

                for comment in comments:
                    comment_timestamp = parser.parse(comment['timestamp']).replace(tzinfo=timezone.utc)
                    
                    if comment_timestamp > self.last_fetch_time:
                        # Process new comment
                        clean_text = self.clean_text(comment.get('text'))
                        vector = {
                            'id': comment['id'],
                            'values': self.generate_embedding(clean_text),
                            'metadata': {
                                'type': 'comment',
                                'timestamp': comment['timestamp'],
                                'post_id': post['id'],
                                'username': comment.get('username', 'unknown_user'),
                                'text': clean_text
                            }
                        }
                        vectors.append(vector)
                        comment_data = {
                            'id': comment['id'],
                            'post_id': post['id'],
                            'text': comment.get('text'),
                            'timestamp': comment['timestamp'],
                            'username': comment.get('username', 'unknown_user'),
                            'replied': False
                        }
                        self.supabase.table('comments').upsert(comment_data, on_conflict='id').execute()

                    # Process replies
                    if 'replies' in comment and 'data' in comment['replies']:
                        for reply_data in comment['replies']['data']:
                            full_reply = self.fetch_reply(reply_data['id'])
                            if full_reply:
                                reply_timestamp = parser.parse(full_reply['timestamp']).replace(tzinfo=timezone.utc)
                                
                                if reply_timestamp > self.last_fetch_time:
                                    # Process new reply
                                    clean_reply_text = self.clean_text(full_reply.get('text'))
                                    reply_vector = {
                                        'id': full_reply['id'],
                                        'values': self.generate_embedding(clean_reply_text),
                                        'metadata': {
                                            'type': 'reply',
                                            'timestamp': full_reply['timestamp'],
                                            'post_id': post['id'],
                                            'parent_comment_id': comment['id'],
                                            'username': full_reply.get('username', 'unknown_user'),
                                            'text': clean_reply_text
                                        }
                                    }
                                    vectors.append(reply_vector)
                                    reply_data = {
                                        'id': full_reply['id'],
                                        'post_id': post['id'],
                                        'parent_comment_id': comment['id'],
                                        'text': full_reply.get('text'),
                                        'timestamp': full_reply['timestamp'],
                                        'username': full_reply.get('username', 'unknown_user'),
                                        'replied': False
                                    }
                                    self.supabase.table('comments').upsert(reply_data, on_conflict='id').execute()

                time.sleep(self.rate_limit_delay)
            except Exception as e:
                logger.error(f"Error processing post {post['id']}: {str(e)}")

        if vectors:
            logger.info(f"Uploading {len(vectors)} vectors to Pinecone")
            self.pinecone_index.upsert(vectors=vectors)
        else:
            logger.info("No new data to process and upload")

    def fetch_all_posts(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/me/media"
        params = {
            "fields": "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count",
            "access_token": self.instagram_access_token,
            "limit": 100  # Maximum allowed by Instagram API
        }
        return self._make_paginated_request(url, params)

    def fetch_reply(self, reply_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/{reply_id}"
        params = {
            "fields": "id,text,timestamp,username",
            "access_token": self.instagram_access_token
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to fetch reply {reply_id}: {response.status_code}")
            return None

    def run(self):
        try:
            self.process_and_upload_data()
            self.save_last_fetch_time()
            logger.info("Data pipeline completed successfully")
        except Exception as e:
            logger.error(f"Error in data pipeline: {str(e)}")
            raise

def main(event, context):
    try:
        load_dotenv()
        pipeline = InstagramDataPipelineV2()
        pipeline.run()
        return "Data pipeline completed successfully", 200
    except Exception as e:
        logger.error(f"Error in data pipeline: {str(e)}")
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    main(None, None)
