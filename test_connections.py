import os
import requests
from dotenv import load_dotenv
from supabase import create_client, Client
from pinecone import Pinecone
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_instagram_connection():
    logger.info("Testing Instagram connection...")
    instagram_access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
    if not instagram_access_token:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN not found in environment variables")
    
    base_url = "https://graph.instagram.com/v17.0"
    
    try:
        url = f"{base_url}/me"
        params = {
            "fields": "id,username",
            "access_token": instagram_access_token
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        user_data = response.json()
        logger.info(f"Successfully connected to Instagram API")
        logger.info(f"User ID: {user_data.get('id')}")
        logger.info(f"Username: {user_data.get('username')}")
        
        media_url = f"{base_url}/me/media"
        media_params = {
            "fields": "id,caption",
            "limit": 1,
            "access_token": instagram_access_token
        }
        
        media_response = requests.get(media_url, params=media_params)
        media_response.raise_for_status()
        
        media_data = media_response.json()
        if media_data.get('data'):
            logger.info("Successfully fetched recent media")
            logger.info(f"Most recent post ID: {media_data['data'][0].get('id')}")
        else:
            logger.info("No recent media found")
        
        logger.info("Instagram connection test completed successfully")
    except Exception as e:
        logger.error(f"Error testing Instagram connection: {str(e)}")

def test_supabase_connection():
    logger.info("Testing Supabase connection...")
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY not found in environment variables")
    
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        logger.info("Successfully connected to Supabase")
        
        try:
            posts_count = supabase.table('posts').select('id', count='exact').execute()
            logger.info(f"Number of rows in 'posts' table: {posts_count.count}")
        except Exception as e:
            logger.warning(f"Could not fetch posts count: {str(e)}")

        try:
            comments_count = supabase.table('comments').select('id', count='exact').execute()
            logger.info(f"Number of rows in 'comments' table: {comments_count.count}")
        except Exception as e:
            logger.warning(f"Could not fetch comments count: {str(e)}")

        try:
            last_fetch_time = supabase.table('metadata').select('value').eq('key', 'last_fetch_time').execute()
            if last_fetch_time.data:
                logger.info(f"Last fetch time: {last_fetch_time.data[0]['value']}")
            else:
                logger.info("Last fetch time not found in metadata table")
        except Exception as e:
            logger.warning(f"Could not fetch last_fetch_time: {str(e)}")
        
        logger.info("Supabase connection test completed successfully")
    except Exception as e:
        logger.error(f"Error testing Supabase connection: {str(e)}")

def test_pinecone_connection():
    logger.info("Testing Pinecone connection...")
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        raise ValueError("PINECONE_API_KEY not found in environment variables")
    
    try:
        pc = Pinecone(api_key=pinecone_api_key)
        indexes = pc.list_indexes()
        logger.info(f"Successfully connected to Pinecone")
        logger.info(f"Available indexes: {indexes.names()}")
        
        index_name = "instagram-data"
        if index_name in indexes.names():
            logger.info(f"Index '{index_name}' found")
            index = pc.Index(index_name)
            stats = index.describe_index_stats()
            logger.info(f"Index stats: {stats}")
        else:
            logger.warning(f"Index '{index_name}' not found")
        
        logger.info("Pinecone connection test completed successfully")
    except Exception as e:
        logger.error(f"Error testing Pinecone connection: {str(e)}")

def main():
    load_dotenv()
    
    test_instagram_connection()
    print("\n" + "-"*50 + "\n")
    test_supabase_connection()
    print("\n" + "-"*50 + "\n")
    test_pinecone_connection()

if __name__ == "__main__":
    main()
