import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.embeddings import MyEmbedder


class EmbeddingModelResponseTests(unittest.TestCase):
    def _response(self, model, count=1):
        body = json.dumps({
            'model': model,
            'data': [{'index': index, 'embedding': [0.1, 0.2, 0.3]}
                     for index in range(count)],
        }).encode()
        return io.BytesIO(body)

    def test_accepts_case_variation_in_returned_model(self):
        with tempfile.TemporaryDirectory() as cache_dir, \
                patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}), \
                patch('src.embeddings.urlopen', return_value=self._response('BAAI/bge-m3')):
            embedder = MyEmbedder('baai/bge-m3', Path(cache_dir), allow_api=True, dimensions=3)

            self.assertEqual(embedder.embed_documents(['text']), [[0.1, 0.2, 0.3]])

    def test_accepts_provider_alias_for_bge_m3(self):
        with tempfile.TemporaryDirectory() as cache_dir, \
                patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}), \
                patch('src.embeddings.urlopen', return_value=self._response('parasail-bge-m3')):
            embedder = MyEmbedder('baai/bge-m3', Path(cache_dir), allow_api=True, dimensions=3)

            self.assertEqual(embedder.embed_documents(['text']), [[0.1, 0.2, 0.3]])
            self.assertEqual(embedder.usage[0]['model'], 'baai/bge-m3')
            self.assertEqual(embedder.usage[0]['returned_model'], 'parasail-bge-m3')

    def test_batches_inputs_in_groups_of_16(self):
        responses = [self._response('baai/bge-m3', 16), self._response('baai/bge-m3', 4)]
        with tempfile.TemporaryDirectory() as cache_dir, \
                patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}), \
                patch('src.embeddings.urlopen', side_effect=responses) as urlopen:
            embedder = MyEmbedder('baai/bge-m3', Path(cache_dir), allow_api=True, dimensions=3)

            vectors = embedder.embed_documents([f'text-{index}' for index in range(20)])

            self.assertEqual(len(vectors), 20)
            self.assertEqual(
                [len(json.loads(call.args[0].data)['input']) for call in urlopen.call_args_list],
                [16, 4],
            )

    def test_rejects_a_different_returned_model_with_details(self):
        with tempfile.TemporaryDirectory() as cache_dir, \
                patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}), \
                patch('src.embeddings.urlopen', return_value=self._response('other/model')):
            embedder = MyEmbedder('baai/bge-m3', Path(cache_dir), allow_api=True, dimensions=3)

            with self.assertRaisesRegex(ValueError, "returned model 'other/model'.*'baai/bge-m3'"):
                embedder.embed_documents(['text'])

            self.assertEqual(list(Path(cache_dir).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
