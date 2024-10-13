# Instagram Data Pipeline

This project implements a data pipeline that fetches Instagram posts, comments, and replies, processes them, and stores the data in Supabase and Pinecone.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Setup](#local-setup)
3. [Database Setup](#database-setup)
4. [Testing](#testing)
5. [Deployment to Google Cloud Functions](#deployment-to-google-cloud-functions)

## Prerequisites

- Python 3.8+
- Instagram Graph API access and token
- Supabase account and project
- Pinecone account and API key
- OpenAI API key
- Google Cloud account (for deployment)

## Local Setup

1. Clone the repository: `git clone https://github.com/yourusername/instagram-data-pipeline.git
cd instagram-data-pipeline  `

2. Create a virtual environment and activate it: `` python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`   ``

3. Install the required packages: `pip install -r requirements.txt  `

4. Create a `.env` file in the project root and add the following environment variables: `INSTAGRAM_ACCESS_TOKEN=your_instagram_access_token
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_api_key
PINECONE_API_KEY=your_pinecone_api_key
OPENAI_API_KEY=your_openai_api_key  `

## Database Setup

1. Connect to your Supabase project using the SQL Editor.

2. Create the necessary tables by running the following SQL commands:

   ````sql
   -- Create posts table
   CREATE TABLE IF NOT EXISTS posts (
       id TEXT PRIMARY KEY,
       caption TEXT,
       media_type TEXT,
       media_url TEXT,
       permalink TEXT,
       timestamp TIMESTAMP WITH TIME ZONE,
       like_count INTEGER,
       comments_count INTEGER
   );

   -- Create comments table
   CREATE TABLE IF NOT EXISTS comments (
       id TEXT PRIMARY KEY,
       post_id TEXT REFERENCES posts(id),
       text TEXT,
       username TEXT,
       timestamp TIMESTAMP WITH TIME ZONE,
       replied BOOLEAN DEFAULT FALSE,
       parent_comment_id TEXT
   );

   -- Create metadata table
   CREATE TABLE IF NOT EXISTS metadata (
       key TEXT PRIMARY KEY,
       value TEXT
   );

   -- Insert initial last_fetch_time
   INSERT INTO metadata (key, value)
   VALUES ('last_fetch_time', '1970-01-01T00:00:00+00:00')
   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;   ```

   ````

3. To reset the data for a new user or fresh start, run the following SQL commands:

   ````sql
   -- Clear existing data
   TRUNCATE TABLE comments;
   TRUNCATE TABLE posts;

   -- Reset last_fetch_time
   UPDATE metadata
   SET value = '1970-01-01T00:00:00+00:00'
   WHERE key = 'last_fetch_time';   ```
   ````

## Testing

1. Run the connection tests to ensure all services are properly configured: `python test_connections.py  `

2. Run the unit tests for the Instagram Data Pipeline: `python -m unittest test_instagram_data_pipeline.py  `

3. If all tests pass, you can run the pipeline locally: `python instagram_data_pipeline_v2.py  `

## Deployment to Google Cloud Functions

1. Install the Google Cloud SDK and initialize it.

2. Create a new Google Cloud project or select an existing one.

3. Enable the Cloud Functions API for your project.

4. Modify the `instagram_data_pipeline_v2.py` file to include the `requirements.txt` content at the top of the file as comments:

   ````python
   # requirements.txt
   # supabase==2.8.1
   # pinecone-client==3.0.0
   # openai==1.3.0
   # python-dotenv==1.0.0
   # emoji==2.8.0
   # python-dateutil==2.8.2

   import os
   import logging
   # ... (rest of the file content)   ```

   ````

5. Deploy the function using the following command: `gcloud functions deploy instagram_data_pipeline \
  --runtime python39 \
  --trigger-http \
  --allow-unauthenticated \
  --entry-point main \
  --set-env-vars INSTAGRAM_ACCESS_TOKEN=your_instagram_access_token,SUPABASE_URL=your_supabase_project_url,SUPABASE_KEY=your_supabase_api_key,PINECONE_API_KEY=your_pinecone_api_key,OPENAI_API_KEY=your_openai_api_key  `

6. Set up a Cloud Scheduler job to trigger the function every 15 minutes: `gcloud scheduler jobs create http instagram_data_pipeline_job \
  --schedule "*/15 * * * *" \
  --uri "YOUR_FUNCTION_URL" \
  --http-method POST  `

   Replace `YOUR_FUNCTION_URL` with the URL of your deployed Cloud Function.

7. Your Instagram Data Pipeline is now deployed and will run every 15 minutes!

## Monitoring and Maintenance

- Monitor the Cloud Function logs for any errors or issues.
- Regularly check your Supabase and Pinecone usage to ensure you're within your plan limits.
- Update your Instagram access token when necessary to maintain API access.

For any questions or issues, please open a GitHub issue or contact the project maintainer.
