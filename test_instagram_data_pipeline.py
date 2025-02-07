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
        mock_pinecone.return_value.Index.return_value = self.mock_pinecone
        
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
        self.assertEqual(cleaned_text, "hello world waving_hand")

    @patch.object(InstagramDataPipelineV2, 'fetch_all_posts')
    @patch.object(InstagramDataPipelineV2, 'fetch_comments')
    @patch.object(InstagramDataPipelineV2, 'fetch_reply')
    @patch.object(InstagramDataPipelineV2, 'generate_embedding')
    def test_process_and_upload_data(self, mock_generate_embedding, mock_fetch_reply, mock_fetch_comments, mock_fetch_all_posts):
        mock_fetch_all_posts.return_value = [
            {'id': '1', 'caption': 'Test post', 'timestamp': '2023-01-01T00:00:00+0000'}
        ]
        mock_fetch_comments.return_value = [
            {'id': 'c1', 'text': 'Test comment', 'timestamp': '2023-01-01T00:00:00+0000', 'replies': {'data': [{'id': 'r1'}]}}
        ]
        mock_fetch_reply.return_value = {
            'id': 'r1', 'text': 'Test reply', 'timestamp': '2023-01-01T00:00:00+0000'
        }
        mock_generate_embedding.return_value = [0.1, 0.2, 0.3]

        self.pipeline.process_and_upload_data()

        # Check that upsert was called for posts, comments, and replies
        self.mock_supabase.table().upsert.assert_any_call(
            {'id': '1', 'caption': 'Test post', 'timestamp': '2023-01-01T00:00:00+0000'},
            on_conflict='id'
        )
        self.mock_supabase.table().upsert.assert_any_call(
            {'id': 'c1', 'post_id': '1', 'text': 'Test comment', 'timestamp': '2023-01-01T00:00:00+0000', 'username': 'unknown_user', 'replied': False},
            on_conflict='id'
        )
        self.mock_supabase.table().upsert.assert_any_call(
            {'id': 'r1', 'post_id': '1', 'parent_comment_id': 'c1', 'text': 'Test reply', 'timestamp': '2023-01-01T00:00:00+0000', 'username': 'unknown_user', 'replied': False},
            on_conflict='id'
        )

        # Check that Pinecone upsert was called with the correct vectors
        expected_vectors = [
            {
                'id': '1',
                'values': [0.1, 0.2, 0.3],
                'metadata': {
                    'type': 'post',
                    'timestamp': '2023-01-01T00:00:00+0000',
                    'likes': 0,
                    'comments': 0,
                    'text': 'test post'
                }
            },
            {
                'id': 'c1',
                'values': [0.1, 0.2, 0.3],
                'metadata': {
                    'type': 'comment',
                    'timestamp': '2023-01-01T00:00:00+0000',
                    'post_id': '1',
                    'username': 'unknown_user',
                    'text': 'test comment'
                }
            },
            {
                'id': 'r1',
                'values': [0.1, 0.2, 0.3],
                'metadata': {
                    'type': 'reply',
                    'timestamp': '2023-01-01T00:00:00+0000',
                    'post_id': '1',
                    'parent_comment_id': 'c1',
                    'username': 'unknown_user',
                    'text': 'test reply'
                }
            }
        ]
        self.mock_pinecone.upsert.assert_called_with(vectors=expected_vectors)

if __name__ == '__main__':
    unittest.main()
