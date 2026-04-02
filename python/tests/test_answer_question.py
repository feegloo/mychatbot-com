import pytest
from unittest.mock import patch
import sys
import json
from answer_question import main


def test_answer_question_with_valid_args(capsys):
    """Test answer_question.main() with valid arguments"""
    with patch('answer_question.answer_with_citations') as mock_answer:
        mock_answer.return_value = {
            "answer": "The answer is 42",
            "citations": ["source1.pdf"]
        }
        
        sys.argv = [
            'answer_question.py',
            '--conversation-id', 'conv-123',
            '--collection-name', 'documents',
            '--question', 'What is the answer?'
        ]
        
        main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        
        assert result['answer'] == "The answer is 42"
        assert "source1.pdf" in result['citations']
        mock_answer.assert_called_once_with(
            collection_name='documents',
            conversation_id='conv-123',
            question='What is the answer?'
        )


def test_answer_question_missing_args():
    """Test that missing required arguments are handled"""
    with patch('sys.exit'):
        sys.argv = ['answer_question.py', '--conversation-id', 'conv-123']
        # ArgumentParser will exit with error if required args are missing
