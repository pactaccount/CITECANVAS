import pytest
from backend.src.runtime import Runtime


def record(char, text):
    return {'docId':char*64,'filename':char+'.pdf','totalPages':1,'pageText':{'1':text}}


def test_sources_reject_unknown_and_path_traversal(tmp_path):
    runtime=Runtime(tmp_path,lambda:[record('a','first')])
    for ids in [[],['../source'],['b'*64],None]:
        with pytest.raises(ValueError):runtime.sources(ids)


def test_comparison_uses_requested_files_and_real_text(tmp_path):
    runtime=Runtime(tmp_path,lambda:[record('a','Pressure 30 bar'),record('b','Pressure 40 bar')])
    result=runtime.compare(['a'*64,'b'*64])
    assert result['changes'][0]['before']=='Pressure 30 bar'
    assert result['changes'][0]['after']=='Pressure 40 bar'
    assert result['changes'][0]['sourceB']['fileId']=='b'*64
    with pytest.raises(ValueError):runtime.compare(['a'*64,'a'*64])


def test_identical_text_has_no_changes_and_scans_fail_honestly(tmp_path):
    runtime=Runtime(tmp_path,lambda:[record('a','same'),record('b','same'),record('c','')])
    assert runtime.compare(['a'*64,'b'*64])['changes']==[]
    with pytest.raises(ValueError):runtime.compare(['a'*64,'c'*64])


def test_unknown_lot_never_retrieves_another_lot(tmp_path,monkeypatch):
    runtime=Runtime(tmp_path,lambda:[record('a','Lot 12345678 pressure 30 bar')])
    monkeypatch.setattr(runtime,'semantic',lambda *_:pytest.fail('Must abstain before model retrieval'))
    candidates,_=runtime.retrieve(runtime.sources(['a'*64]),'What is the pressure for lot 99988877?')
    assert candidates==[]


def test_text_first_retrieval_does_not_require_visual_embeddings(tmp_path, monkeypatch):
    runtime = Runtime(tmp_path, lambda: [record('a', 'The tested temperature is 25 C.')])
    monkeypatch.setattr(runtime, 'semantic', lambda *_: pytest.fail('visual retrieval must stay deferred'))
    candidates, warnings = runtime.retrieve(runtime.sources(['a' * 64]), 'What is the tested temperature?', include_semantic=False)
    assert candidates[0][2] == 1
    assert warnings == []


def test_missing_model_key_and_empty_input_have_no_sample_fallback(tmp_path,monkeypatch):
    monkeypatch.delenv('VLM_API_KEY',raising=False)
    runtime=Runtime(tmp_path,lambda:[record('a','text')])
    with pytest.raises(ValueError):runtime.ask(['a'*64],'')
    with pytest.raises(RuntimeError):runtime.ask(['a'*64],'Question')
    with pytest.raises(ValueError):runtime.extract(['a'*64],[])
