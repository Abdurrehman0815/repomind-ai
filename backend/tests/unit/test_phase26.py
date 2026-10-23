from app.services.evaluation_service import EvaluationService

def test_evaluation_measures_terms_and_citations():
    result = EvaluationService.evaluate("The login is in auth.", [{"file_path":"app/auth.py"}], {"id":"x","required_terms":["login"],"expected_files":["app/auth.py"]})
    assert result["passed"] is True
    assert result["term_recall"] == result["citation_recall"] == 1.0
