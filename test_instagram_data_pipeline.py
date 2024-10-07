import unittest
from unittest.mock import patch, MagicMock
from instagram_data_pipeline_v2 import InstagramDataPipelineV2
from datetime import datetime, timezone

class TestInstagramDataPipelineV2(unittest.TestCase):

    @patch('instagram_data_pipeline_v2.create_client')
    @patch('instagram_data_pipeline_v2.OpenAI')
    @patch('instagram_data_pipeline_v2.Pinecone')
    def setUp(self, mock_pinecone, mock_openai, mock_supabase):
        self.mock_supabase = MagicMock()
        mock_supabase.return_value = self.mock_supabase
        self.mock_openai = MagicMock()
        mock_openai.return_value = self.mock_openai
        self.mock_pinecone = MagicMock()
        mock_pinecone.return_value.Index.return_value = self.mock_pinecone  # Update this line
        
        # Mock the load_last_fetch_time method
        with patch.object(InstagramDataPipelineV2, 'load_last_fetch_time', return_value=datetime.min.replace(tzinfo=timezone.utc)):
            self.pipeline = InstagramDataPipelineV2()

    def test_load_last_fetch_time(self):
        mock_result = MagicMock()
        mock_result.data = [{'value': '2023-01-01T00:00:00+00:00'}]
        self.mock_supabase.table().select().eq().execute.return_value = mock_result

        result = self.pipeline.load_last_fetch_time()
        self.assertEqual(result, datetime(2023, 1, 1, tzinfo=timezone.utc))

    @patch('instagram_data_pipeline_v2.requests.get')
    def test_make_paginated_request(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'data': [{'id': '1', 'caption': 'Test post'}],
            'paging': {'next': None}
        }
        mock_get.return_value = mock_response

        result = self.pipeline._make_paginated_request('https://test.com', {})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], '1')

    def test_clean_text(self):
        text = "Hello, World! 👋 https://example.com"
        cleaned_text = self.pipeline.clean_text(text)
        self.assertEqual(cleaned_text, "hello world :waving_hand:")  # Update this line

    @patch.object(InstagramDataPipelineV2, 'fetch_posts')
    @patch.object(InstagramDataPipelineV2, 'fetch_comments')
    @patch.object(InstagramDataPipelineV2, 'generate_embedding')
    def test_process_and_upload_data(self, mock_generate_embedding, mock_fetch_comments, mock_fetch_posts):
        mock_fetch_posts.return_value = [
            {'id': '1', 'caption': 'Test post', 'timestamp': '2023-01-01T00:00:00+0000'}
        ]
        mock_fetch_comments.return_value = [
            {'id': 'c1', 'text': 'Test comment', 'timestamp': '2023-01-01T00:00:00+0000'}
        ]
        mock_generate_embedding.return_value = [0.1, 0.2, 0.3]

        self.pipeline.process_and_upload_data()

        self.mock_supabase.table().upsert.assert_called()
        self.mock_pinecone.upsert.assert_called()

if __name__ == '__main__':
    unittest.main()