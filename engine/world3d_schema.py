"""Canonical JSON Schema shared by REST, MCP, saved documents and the UI.

No executable expressions, external references, network locations or plug-ins.
A schema-valid document still undergoes semantic/lifecycle validation.
"""
from copy import deepcopy


def obj(properties, required=()):
    return {"type":"object","properties":properties,"required":list(required),"additionalProperties":False}


def num(low=-10000,high=10000): return {"type":"number","minimum":low,"maximum":high}

def vec(low=-10000,high=10000):
    return {"type":"array","items":num(low,high),"minItems":3,"maxItems":3}

IDENTITY={"type":"string","pattern":"^[A-Za-z0-9_-]{1,64}$"}
TEXT={"type":"string","minLength":1,"maxLength":500}
LABELS={"type":"array","items":TEXT,"maxItems":24}
QUAT={"type":"array","items":num(-1,1),"minItems":4,"maxItems":4}
POSE=obj({"position_m":vec(),"orientation_wxyz":QUAT},["position_m"])
GEOMETRY={"oneOf":[
    obj({"kind":{"const":"sphere"},"radius_m":num(.001,100)},["kind","radius_m"]),
    obj({"kind":{"const":"box"},"half_extents_m":vec(.001,100)},["kind","half_extents_m"]),
    obj({"kind":{"const":"capsule"},"radius_m":num(.001,100),"half_length_m":num(0,100)},["kind","radius_m","half_length_m"]),
]}
PROFILE=obj({
    "schema_version":{"const":"2.0"},
    "motion_model":{"enum":["static","constant_acceleration","ground","ballistic","ground_air_hybrid","prismatic"]},
    "mass_kg":num(.001,1e6),"inertia_kg_m2":vec(.000001,1e8),
    "max_horizontal_speed_mps":num(0,200),"max_vertical_speed_mps":num(0,100),
    "max_acceleration_mps2":num(.001,100),"max_angular_speed_radps":num(0,20),
    "gravity_mps2":num(0,30),"linear_drag_per_s":num(0,10),
    "thrust_n":vec(-1e8,1e8),"max_payload_kg":num(0,1e6),
    "elevated_above_m":num(0,100),"elevated_speed_limit_mps":num(0,100),
    "hypothetical":{"type":"boolean"},"assumptions":LABELS,
},["schema_version","motion_model","mass_kg","max_horizontal_speed_mps","max_vertical_speed_mps","max_acceleration_mps2","gravity_mps2","assumptions"])
JOINT=obj({"type":{"const":"prismatic_z"},"start_s":num(0,30),"initial_m":num(0,100),
           "target_m":num(0,100),"max_travel_m":num(.001,100),"speed_mps":num(.001,10),
           "acceleration_mps2":num(.001,20)},["type","start_s","initial_m","target_m","max_travel_m","speed_mps","acceleration_mps2"])
BODY=obj({"id":IDENTITY,"label":TEXT,"pose":POSE,"velocity_mps":vec(-200,200),
          "acceleration_mps2":vec(-100,100),"angular_velocity_radps":vec(-20,20),
          "geometry":GEOMETRY,"physics":PROFILE,"parent_id":IDENTITY,"joint":JOINT,
          "attachment":{"const":"rigid_assumption"},"provenance":{"enum":["MODEL_DERIVED","DETERMINISTIC","FIXTURE","ASSUMPTION","HARDWARE_OBSERVATION"]},
          "uncertainty_radius_m":num(0,100)},["id","pose","geometry","physics","provenance"])
CALIBRATION=obj({"status":{"enum":["ASSUMPTION_3D","CALIBRATED_METRIC_3D","ESTIMATED_3D"]},
                 "method":{"enum":["simulation","declared_scale","depth_sensor","stereo","surveyed_geometry"]},
                 "evidence_id":TEXT,"uncertainty_m":num(0,100),"assumptions":LABELS},
                ["status","method","uncertainty_m","assumptions"])
SCENE=obj({"schema_version":{"const":"2.0"},"coordinate_frame":{"const":"world_enu"},"units":{"const":"SI"},
           "name":TEXT,"calibration":CALIBRATION,"duration_s":num(.01,30),"step_s":num(.01,.25),
           "objects":{"type":"array","items":BODY,"minItems":1,"maxItems":16},
           "excluded_pairs":{"type":"array","items":{"type":"array","items":IDENTITY,"minItems":2,"maxItems":2},"maxItems":32},
           "assumptions":LABELS},["schema_version","coordinate_frame","units","name","calibration","duration_s","step_s","objects","assumptions"])


def validate(schema, value):
    import jsonschema
    try: jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as error:
        location=".".join(str(p) for p in error.absolute_path)
        raise ValueError(f"invalid 3D contract at {location or 'root'}: {error.validator}") from None
    return deepcopy(value)
