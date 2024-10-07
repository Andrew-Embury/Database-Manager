# Instagram Data Collection and Vectorization Project

## Project Overview

This project automates the collection, processing, and vectorization of Instagram post data. It fetches the latest posts and comments, processes the text, generates embeddings, and stores the data in both a Supabase database and a Pinecone vector database. The system is designed to run periodically on Google Cloud Functions, keeping the data up-to-date for use in AI-driven applications.

## Features

- Fetches recent Instagram posts and comments using the Instagram Graph API
- Processes and cleans text data, including emoji handling
- Generates text embeddings using OpenAI's API
- Stores raw data in Supabase and vector embeddings in Pinecone
- Implements pagination and error handling for robust data collection
- Designed for deployment on Google Cloud Functions with scheduled execution

## Tech Stack

- Python 3.9+
- Instagram Graph API
- Supabase (PostgreSQL database)
- OpenAI API (for text embeddings)
- Pinecone (vector database)
- Google Cloud Functions
- Google Cloud Scheduler

## Project Structure

- `instagram_data_pipeline_v2.py`: Main script containing the data pipeline logic
- `test_instagram_data_pipeline.py`: Unit tests for the data pipeline
- `requirements.txt`: List of Python dependencies
- `README.md`: This file, containing project documentation

## Setup and Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/your-username/instagram-data-project.git
   cd instagram-data-project
   ```

2. **Set up a virtual environment and install dependencies:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**
   Create a `.env` file in the project root with the following variables:

   ```plaintext
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_key
   OPENAI_API_KEY=your_openai_api_key
   PINECONE_API_KEY=your_pinecone_api_key
   INSTAGRAM_ACCESS_TOKEN=your_instagram_access_token
   ```

## Local Development and Testing

To run the script locally:

```bash
python instagram_data_pipeline_v2.py
```

To run the unit tests:

```bash
python -m unittest test_instagram_data_pipeline.py
```

## Deploying to Google Cloud Platform (GCP)

1. **Install and initialize the Google Cloud SDK:**

   - Download and install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install).
   - Initialize the SDK with your Google account:

     ```bash
     gcloud init
     ```

2. **Set your project ID:**

   ```bash
   gcloud config set project YOUR_PROJECT_ID
   ```

3. **Enable necessary APIs:**

   ```bash
   gcloud services enable cloudfunctions.googleapis.com cloudscheduler.googleapis.com
   ```

4. **Deploy the function:**

   ```bash
   gcloud functions deploy instagram_data_pipeline \
     --runtime python39 \
     --trigger-http \
     --entry-point main \
     --memory 256MB \
     --timeout 540s \
     --set-env-vars SUPABASE_URL=your_supabase_url,SUPABASE_KEY=your_supabase_key,OPENAI_API_KEY=your_openai_api_key,PINECONE_API_KEY=your_pinecone_api_key,INSTAGRAM_ACCESS_TOKEN=your_instagram_access_token
   ```

   Note: Replace the environment variable values with your actual credentials.

5. **Set up Cloud Scheduler for periodic execution:**

   ```bash
   gcloud scheduler jobs create http instagram_data_pipeline_hourly \
     --schedule "0 * * * *" \
     --uri "https://REGION-PROJECT_ID.cloudfunctions.net/instagram_data_pipeline" \
     --http-method POST
   ```

   Replace `REGION` and `PROJECT_ID` with your actual Google Cloud region and project ID.

## Monitoring and Maintenance

- View logs in the Google Cloud Console under "Cloud Functions" > "instagram_data_pipeline" > "Logs"
- Regularly check for updates to the Instagram Graph API and adjust the code if necessary
- Monitor usage and costs for OpenAI API, Pinecone, and Google Cloud services

## Troubleshooting

- Ensure all environment variables are correctly set in the Cloud Function configuration
- Check Cloud Function logs for detailed error messages
- Verify that the Instagram access token is valid and has the necessary permissions

## Contributing

Please read CONTRIBUTING.md for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the LICENSE.md file for details.
