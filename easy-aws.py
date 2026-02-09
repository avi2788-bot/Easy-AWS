#!/usr/bin/env python3
import boto3
import argparse
import getpass
from botocore.exceptions import ClientError

# --- Configuration & Guardrails ---
# Rebranded tag value
APP_TAG_KEY = 'CreatedBy'
APP_TAG_VALUE = 'easy-aws'
OWNER_TAG_KEY = 'Owner'
CURRENT_USER = getpass.getuser()

ALLOWED_INSTANCE_TYPES = ['t3.micro', 't2.small']
EC2_RUNNING_CAP = 2

# Initialize Boto3 Clients
ec2_client = boto3.client('ec2')
s3_client = boto3.client('s3')
r53_client = boto3.client('route53')


# --- Helper Functions ---

def get_common_tags():
    """Returns standard tags to apply to all resources."""
    return [
        {'Key': APP_TAG_KEY, 'Value': APP_TAG_VALUE},
        {'Key': 'Name', 'Value': f'{CURRENT_USER}_Resource'},
        {'Key': OWNER_TAG_KEY, 'Value': CURRENT_USER}
    ]


def validate_cli_resource(tags):
    """Checks if a resource has the specific easy-aws tag."""
    if not tags:
        return False
    for tag in tags:
        if tag['Key'] == APP_TAG_KEY and tag['Value'] == APP_TAG_VALUE:
            return True
    return False


# --- EC2 Module ---

def get_latest_ami(os_type):
    """Fetches latest AMI ID for Ubuntu or Amazon Linux 2."""
    if os_type == 'ubuntu':
        # Canonical (Ubuntu) Owner ID: 099720109477
        filters = [{'Name': 'name', 'Values': ['ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*']}]
        owner = '099720109477'
    else:
        # Amazon Linux 2
        filters = [{'Name': 'name', 'Values': ['amzn2-ami-hvm-*-x86_64-gp2']}]
        owner = 'amazon'

    response = ec2_client.describe_images(Filters=filters, Owners=[owner])
    # Sort by creation date desc and take the first
    images = sorted(response['Images'], key=lambda k: k['CreationDate'], reverse=True)
    if not images:
        raise Exception(f"No AMI found for {os_type}")
    return images[0]['ImageId']


def check_ec2_cap():
    """Enforces the hard cap on running instances."""
    response = ec2_client.describe_instances(
        Filters=[
            {'Name': f'tag:{APP_TAG_KEY}', 'Values': [APP_TAG_VALUE]},
            {'Name': 'instance-state-name', 'Values': ['running', 'pending']}
        ]
    )
    count = sum(len(r['Instances']) for r in response['Reservations'])
    if count >= EC2_RUNNING_CAP:
        raise Exception(f"❌ Creation Denied: Hard cap of {EC2_RUNNING_CAP} running instances reached.")
    return True


def ec2_manager(args):
    if args.action == 'create':
        print(f"⚙️  EasyAWS: Provisioning EC2 ({args.type}, {args.os})...")
        try:
            check_ec2_cap()
            if args.type not in ALLOWED_INSTANCE_TYPES:
                print(f"❌ Error: {args.type} is not allowed. Use: {ALLOWED_INSTANCE_TYPES}")
                return

            ami_id = get_latest_ami(args.os)
            ec2_client.run_instances(
                ImageId=ami_id,
                InstanceType=args.type,
                MinCount=1, MaxCount=1,
                TagSpecifications=[{'ResourceType': 'instance', 'Tags': get_common_tags()}]
            )
            print("✅ Success: Instance launched.")
        except Exception as e:
            print(f"❌ Error: {e}")

    elif args.action == 'list':
        response = ec2_client.describe_instances(
            Filters=[{'Name': f'tag:{APP_TAG_KEY}', 'Values': [APP_TAG_VALUE]}]
        )
        print(f"{'ID':<20} {'Type':<15} {'State':<15} {'Owner':<15}")
        print("-" * 65)
        for r in response['Reservations']:
            for i in r['Instances']:
                owner = next((t['Value'] for t in i.get('Tags', []) if t['Key'] == OWNER_TAG_KEY), 'N/A')
                print(f"{i['InstanceId']:<20} {i['InstanceType']:<15} {i['State']['Name']:<15} {owner:<15}")

    elif args.action in ['start', 'stop']:
        if not args.id:
            print("❌ Error: Instance ID required.")
            return
        try:
            desc = ec2_client.describe_instances(InstanceIds=[args.id])
            tags = desc['Reservations'][0]['Instances'][0].get('Tags', [])

            if not validate_cli_resource(tags):
                print(f"⛔ Access Denied: Instance {args.id} was not created by EasyAWS.")
                return

            if args.action == 'start':
                ec2_client.start_instances(InstanceIds=[args.id])
                print(f"✅ Starting {args.id}...")
            elif args.action == 'stop':
                ec2_client.stop_instances(InstanceIds=[args.id])
                print(f"✅ Stopping {args.id}...")
        except ClientError as e:
            print(f"❌ AWS Error: {e}")


# --- S3 Module ---

def s3_manager(args):
    if args.action == 'create':
        if not args.name:
            print("❌ Error: Bucket name required.")
            return
        acl = 'private'
        if args.public:
            confirm = input(f"⚠️  WARNING: Creating PUBLIC bucket '{args.name}'. Confirm? (yes/no): ")
            if confirm.lower() != 'yes':
                return
            acl = 'public-read'

        try:
            region = boto3.session.Session().region_name or 'us-east-1'
            if region == 'us-east-1':
                s3_client.create_bucket(Bucket=args.name)
            else:
                s3_client.create_bucket(Bucket=args.name, CreateBucketConfiguration={'LocationConstraint': region})

            s3_client.put_bucket_tagging(
                Bucket=args.name,
                Tagging={'TagSet': get_common_tags()}
            )

            if acl == 'public-read':
                try:
                    s3_client.delete_public_access_block(Bucket=args.name)
                    s3_client.put_bucket_acl(Bucket=args.name, ACL='public-read')
                    print(f"⚠️  Bucket is PUBLIC.")
                except Exception as e:
                    print(f"⚠️  Could not set public ACL: {e}")
            print(f"✅ Success: Bucket '{args.name}' created.")
        except ClientError as e:
            print(f"❌ AWS Error: {e}")

    elif args.action == 'list':
        try:
            response = s3_client.list_buckets()
            print(f"{'Bucket Name':<30} {'Creation Date':<30}")
            print("-" * 60)
            for bucket in response['Buckets']:
                try:
                    tags_resp = s3_client.get_bucket_tagging(Bucket=bucket['Name'])
                    if validate_cli_resource(tags_resp['TagSet']):
                        print(f"{bucket['Name']:<30} {str(bucket['CreationDate']):<30}")
                except ClientError:
                    continue
        except ClientError as e:
            print(f"❌ AWS Error: {e}")

    elif args.action == 'upload':
        if not args.name or not args.file:
            print("❌ Error: Bucket name and file path required.")
            return
        try:
            tags_resp = s3_client.get_bucket_tagging(Bucket=args.name)
            if not validate_cli_resource(tags_resp['TagSet']):
                print(f"⛔ Access Denied: Bucket '{args.name}' not owned by EasyAWS.")
                return
            s3_client.upload_file(args.file, args.name, args.file.split('/')[-1])
            print(f"✅ Success: File uploaded.")
        except ClientError as e:
            print(f"❌ Error: {e}")


# --- Route53 Module ---

def r53_manager(args):
    if args.action == 'create-zone':
        if not args.domain:
            print("❌ Error: Domain name required.")
            return
        try:
            ref = str(hash(args.domain))
            resp = r53_client.create_hosted_zone(Name=args.domain, CallerReference=ref)
            zone_id = resp['HostedZone']['Id']
            r53_client.change_tags_for_resource(
                ResourceType='hostedzone', ResourceId=zone_id.split('/')[-1],
                AddTags=get_common_tags()
            )
            print(f"✅ Success: Zone {args.domain} created ({zone_id}).")
        except ClientError as e:
            print(f"❌ AWS Error: {e}")

    elif args.action == 'list':
        resp = r53_client.list_hosted_zones()
        print(f"{'Zone ID':<20} {'Name':<25} {'Private':<10}")
        print("-" * 60)
        for zone in resp['HostedZones']:
            try:
                tags = r53_client.list_tags_for_resource(ResourceType='hostedzone',
                                                         ResourceId=zone['Id'].split('/')[-1])
                if validate_cli_resource(tags['ResourceTagSet']['Tags']):
                    print(
                        f"{zone['Id'].split('/')[-1]:<20} {zone['Name']:<25} {str(zone['Config']['PrivateZone']):<10}")
            except ClientError:
                continue

    elif args.action == 'manage-record':
        if not args.zone_id or not args.record or not args.value:
            print("❌ Error: Zone ID, Record Name, and Value required.")
            return
        try:
            tags = r53_client.list_tags_for_resource(ResourceType='hostedzone', ResourceId=args.zone_id)
            if not validate_cli_resource(tags['ResourceTagSet']['Tags']):
                print(f"⛔ Access Denied: Zone {args.zone_id} not owned by EasyAWS.")
                return

            change_batch = {'Changes': [{'Action': 'UPSERT',
                                         'ResourceRecordSet': {'Name': args.record, 'Type': 'A', 'TTL': 300,
                                                               'ResourceRecords': [{'Value': args.value}]}}]}
            r53_client.change_resource_record_sets(HostedZoneId=args.zone_id, ChangeBatch=change_batch)
            print(f"✅ Success: Record {args.record} updated.")
        except ClientError as e:
            print(f"❌ AWS Error: {e}")


# --- Cleanup Module ---


def cleanup_manager(args):
    """
    DANGER: Deletes ALL resources tagged with CreatedBy=easy-aws
    """
    print("🚨  DANGER ZONE: This will destroy ALL resources created by EasyAWS.")
    print("    - Terminate EC2 instances")
    print("    - Empty and Delete S3 buckets")
    print("    - Delete Route53 Zones")

    confirm = input("Type 'DELETE' to confirm: ")
    if confirm != 'DELETE':
        print("❌ Aborted.")
        return

    print("\n🧹 Starting Cleanup...")

    # --- 1. EC2 Cleanup ---
    try:
        # Find instances
        response = ec2_client.describe_instances(
            Filters=[
                {'Name': f'tag:{APP_TAG_KEY}', 'Values': [APP_TAG_VALUE]},
                {'Name': 'instance-state-name', 'Values': ['running', 'stopped', 'pending']}
            ]
        )
        instance_ids = []
        for r in response['Reservations']:
            for i in r['Instances']:
                instance_ids.append(i['InstanceId'])

        if instance_ids:
            ec2_client.terminate_instances(InstanceIds=instance_ids)
            print(f"🔥 Terminated {len(instance_ids)} EC2 instances: {instance_ids}")
        else:
            print("💨 No EC2 instances found.")
    except Exception as e:
        print(f"❌ EC2 Cleanup Error: {e}")

    # --- 2. S3 Cleanup ---
    try:
        # S3 listing filtering must be done client-side
        all_buckets = s3_client.list_buckets()
        s3_resource = boto3.resource('s3')  # Using resource for easier deletion

        for bucket in all_buckets['Buckets']:
            name = bucket['Name']
            try:
                tags = s3_client.get_bucket_tagging(Bucket=name)
                if validate_cli_resource(tags['TagSet']):
                    print(f"🗑️  Emptying and deleting bucket: {name}...")
                    bucket_res = s3_resource.Bucket(name)
                    # Must delete all objects and versions first!
                    bucket_res.object_versions.delete()
                    bucket_res.objects.all().delete()
                    bucket_res.delete()
                    print(f"✅ Deleted {name}")
            except ClientError:
                # Bucket has no tags or access denied
                continue
    except Exception as e:
        print(f"❌ S3 Cleanup Error: {e}")

    # --- 3. Route53 Cleanup ---
    try:
        zones = r53_client.list_hosted_zones()['HostedZones']
        for zone in zones:
            zone_id = zone['Id'].split('/')[-1]
            try:
                tags = r53_client.list_tags_for_resource(ResourceType='hostedzone', ResourceId=zone_id)
                if validate_cli_resource(tags['ResourceTagSet']['Tags']):
                    print(f"🗑️  Deleting Zone: {zone['Name']}...")

                    # Delete all records except SOA and NS (required to delete zone)
                    records = r53_client.list_resource_record_sets(HostedZoneId=zone_id)
                    changes = []
                    for record in records['ResourceRecordSets']:
                        if record['Type'] not in ['SOA', 'NS']:
                            changes.append({
                                'Action': 'DELETE',
                                'ResourceRecordSet': record
                            })

                    if changes:
                        # Batch delete records
                        r53_client.change_resource_record_sets(
                            HostedZoneId=zone_id,
                            ChangeBatch={'Changes': changes}
                        )

                    # Delete the zone itself
                    r53_client.delete_hosted_zone(Id=zone_id)
                    print(f"✅ Deleted Zone {zone_id}")

            except ClientError:
                continue
    except Exception as e:
        print(f"❌ Route53 Cleanup Error: {e}")

    print("\n✨ Cleanup Complete.")


# --- Main Entrypoint ---

def main():
    parser = argparse.ArgumentParser(prog='EasyAWS', description="EasyAWS CLI - Simplified Cloud Provisioning")
    subparsers = parser.add_subparsers(dest='service', required=True)
    cleanup_parser = subparsers.add_parser('cleanup', help='Delete ALL resources created by EasyAWS')

    # EC2 Parser
    ec2_parser = subparsers.add_parser('ec2', help='Manage EC2')
    ec2_parser.add_argument('action', choices=['create', 'start', 'stop', 'list'])
    ec2_parser.add_argument('--type', default='t3.micro', help='Instance Type')
    ec2_parser.add_argument('--os', choices=['ubuntu', 'amazon'], default='amazon', help='OS Type')
    ec2_parser.add_argument('--id', help='Instance ID')

    # S3 Parser
    s3_parser = subparsers.add_parser('s3', help='Manage S3')
    s3_parser.add_argument('action', choices=['create', 'upload', 'list'])
    s3_parser.add_argument('--name', help='Bucket Name')
    s3_parser.add_argument('--public', action='store_true', help='Make bucket public')
    s3_parser.add_argument('--file', help='File to upload')

    # Route53 Parser
    r53_parser = subparsers.add_parser('r53', help='Manage DNS')
    r53_parser.add_argument('action', choices=['create-zone', 'manage-record', 'list'])
    r53_parser.add_argument('--domain', help='Domain name')
    r53_parser.add_argument('--zone-id', help='Hosted Zone ID')
    r53_parser.add_argument('--record', help='Record Name')
    r53_parser.add_argument('--value', help='Record Value')

    args = parser.parse_args()

    if args.service == 'ec2':
        ec2_manager(args)
    elif args.service == 's3':
        s3_manager(args)
    elif args.service == 'r53':
        r53_manager(args)
    elif args.service == 'cleanup':
        cleanup_manager(args)


if __name__ == "__main__":
    main()
