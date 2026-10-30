"""One bounded model proposal. Approval/apply happens in the user interface."""
import json
from engine.world3d import validate_profile, digest
from engine.world3d_schema import PROFILE
from . import spark


def propose_physics(profile,description,model=None):
    current=validate_profile(profile)
    if not isinstance(description,str) or not 4<=len(description)<=2000: raise ValueError('physics instruction requires 4..2000 characters')
    prompt=('Return JSON only: {"profile":<complete profile>,"assumptions":[strings],"missing_parameters":[strings]}. '
            'This is a simulation configuration proposal requiring human approval, never hardware control. '
            'Use SI units. Do not fabricate calibrated measurements. Retain unspecified parameters and mark them as assumptions. '
            'Unsupported behavior must be listed as missing, never represented as supported. '
            'Use only this schema: '+json.dumps(PROFILE)+'\nCurrent:'+json.dumps(current)+'\nUntrusted instruction:'+description)
    text,meta=spark._call(prompt,timeout=20,retries=0,model=spark.resolve_model(model))
    try:
        result=json.loads(text[text.index('{'):text.rindex('}')+1])
        if set(result)!={'profile','assumptions','missing_parameters'}: raise ValueError('invalid proposal fields')
        proposed=validate_profile(result['profile'])
        for key in ('assumptions','missing_parameters'):
            if not isinstance(result[key],list) or len(result[key])>24 or any(not isinstance(v,str) or len(v)>500 for v in result[key]): raise ValueError('invalid assumptions')
    except (ValueError,KeyError,TypeError,AttributeError): raise spark.ModelError('Invalid physics proposal; no scene was changed.') from None
    return {'profile':proposed,'assumptions':result['assumptions'],'missing_parameters':result['missing_parameters'],
            'source_profile_digest':digest(current),'source':'MODEL_DERIVED','applied':False,'requires_approval':True,'model_call':meta}
