"""ROS 2 Jazzy observation bridge. Publishes state/risks/poses/diagnostics only.

Requires the host's ROS environment. No command, Twist, ros2_control service,
controller-manager switch or hardware-action publisher exists here.
"""
import argparse
import json
from pathlib import Path
import time


def snapshot(path,now=None,max_age_s=2.):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>8*1024*1024:raise ValueError('bounded_runtime_snapshot_required')
    value=json.loads(path.read_text());now=time.time() if now is None else now
    age=now-value.get('updated_unix_s',0)
    fresh=0<=age<=max_age_s and value.get('source_connected') is True and not value.get('stale',True)
    prediction=value.get('prediction')
    metric=bool(prediction and prediction.get('calibration',{}).get('status') in ('CALIBRATED_METRIC_3D','ESTIMATED_3D','ASSUMPTION_3D'))
    return {'schema_version':'2.0','frame_id':'world_enu','fresh':fresh,'age_s':age,'physical_actuation':False,
            'poses':prediction['frames'][0]['objects'] if fresh and metric else [],
            'risks':prediction.get('events',[]) if fresh and prediction else [],'state':value,
            'pose_provenance':prediction.get('calibration',{}).get('status') if prediction else 'PIXEL_ONLY_2D'}


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy
    from geometry_msgs.msg import PoseArray,Pose
    from std_msgs.msg import String
    from diagnostic_msgs.msg import DiagnosticArray,DiagnosticStatus,KeyValue
    parser=argparse.ArgumentParser();parser.add_argument('--state-file',required=True);args=parser.parse_args()
    rclpy.init();node=Node('frontiersight_shadow_bridge')
    qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.BEST_EFFORT,durability=DurabilityPolicy.VOLATILE)
    pose_pub=node.create_publisher(PoseArray,'frontiersight/world_poses',qos)
    state_pub=node.create_publisher(String,'frontiersight/world_state_v2',qos)
    risk_pub=node.create_publisher(String,'frontiersight/risks_v2',qos)
    diagnostics=node.create_publisher(DiagnosticArray,'frontiersight/diagnostics',10)
    def publish():
        try:record=snapshot(args.state_file)
        except (ValueError,OSError):record={'fresh':False,'poses':[],'risks':[],'error':'snapshot_unavailable','physical_actuation':False}
        # Header stamp is publication time. Source media/hardware timestamp and
        # calibration status remain explicit in the versioned state message.
        stamp=node.get_clock().now().to_msg();message=String();message.data=json.dumps(record,allow_nan=False);state_pub.publish(message)
        risk=String();risk.data=json.dumps({'fresh':record['fresh'],'risks':record['risks'],'physical_actuation':False});risk_pub.publish(risk)
        poses=PoseArray();poses.header.frame_id='world_enu';poses.header.stamp=stamp
        for item in record['poses']:
            p=Pose();p.position.x,p.position.y,p.position.z=item['position_m']
            p.orientation.w,p.orientation.x,p.orientation.y,p.orientation.z=item['orientation_wxyz'];poses.poses.append(p)
        pose_pub.publish(poses)
        report=DiagnosticArray();report.header.stamp=stamp;status=DiagnosticStatus();status.name='FrontierSight shadow';status.hardware_id='no_actuator_interface'
        status.level=DiagnosticStatus.OK if record['fresh'] else DiagnosticStatus.WARN;status.message='fresh observations' if record['fresh'] else 'stale or disconnected'
        status.values=[KeyValue(key='actuation',value='disabled'),KeyValue(key='pose_provenance',value=record.get('pose_provenance','unavailable'))];report.status=[status];diagnostics.publish(report)
    node.create_timer(.2,publish)
    try:rclpy.spin(node)
    finally:node.destroy_node();rclpy.shutdown()


if __name__=='__main__':main()
