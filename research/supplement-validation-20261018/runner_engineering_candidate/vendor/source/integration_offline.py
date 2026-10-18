"""This isolated release supports deterministic recorded replay only."""
class ModelExecutionDisabled(RuntimeError): pass

def reject_model_execution(*args, **kwargs):
    raise ModelExecutionDisabled('NEW_MODEL_AND_ENCODER_EXECUTION_DISABLED_IN_ISOLATED_CANDIDATE; use cleareval.py recorded replay commands')

class NoModel:
    model_name='offline-no-model'
    def __getattr__(self,name):
        reject_model_execution()
