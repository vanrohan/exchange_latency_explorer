"""
Exchange Latency Testing Tool

Details: https://vanderwalt.de/blog/exchange-latency-explorer

Usage:
    python main.py [--report-only]

Options:
    --report-only    Only generate the analysis report from existing results
"""

import os
import json
import time
from typing import Optional
import subprocess
import paramiko
from config import Config, load_config
import shutil
import logging
from datetime import datetime
import argparse

DEFAULT_TIMEOUT = 300
DEFAULT_SSH_USERNAME = "ubuntu"
TERRAFORM_TEMPLATE = "terraform_templates/main.tf"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def ssh_wait_for_file(
    hostname: str,
    username: str,
    private_key_path: str,
    remote_path: str,
    filename: str,
    timeout: int = 300,
) -> bool:
    """
    Wait for a file to appear on a remote server via SSH.

    Args:
        hostname: Remote server hostname/IP
        username: SSH username
        private_key_path: Path to private key file
        remote_path: Remote directory path to check
        filename: Name of file to wait for
        timeout: Maximum time to wait in seconds

    Returns:
        bool: True if file was found, False otherwise
    """
    print(f"Waiting for file {filename} on {hostname}...")
    try:
        key = paramiko.RSAKey.from_private_key_file("blog_id_rsa")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                client.connect(hostname=hostname, username=username, pkey=key)
                sftp = client.open_sftp()
                try:
                    if filename in sftp.listdir(remote_path):
                        print(f"File {filename} found!")
                        return True
                finally:
                    sftp.close()
                    client.close()
                time.sleep(5)

            except (
                paramiko.ssh_exception.AuthenticationException,
                paramiko.ssh_exception.SSHException,
            ) as e:
                print(f"SSH connection error: {e}")
                time.sleep(10)
                continue
            except FileNotFoundError:
                print(f"Remote directory {remote_path} not found.")
                return False

        print(f"Timeout waiting for file {filename}")
        return False

    except Exception as e:
        print(f"Error in ssh_wait_for_file: {e}")
        return False


class RegionDeployment:
    """Manages AWS resources and testing for a single region"""

    def __init__(self, config: Config, region: str):
        self.config = config
        self.region = region
        self.terraform_dir = f"terraform_{region}"

    def prepare_terraform_files(self):
        """Prepare terraform files for this region"""
        os.makedirs(self.terraform_dir, exist_ok=True)
        shutil.copy2("blog_id_rsa", f"{self.terraform_dir}/")
        shutil.copy2("blog_id_rsa.pub", f"{self.terraform_dir}/")
        with open("terraform_templates/main.tf", "r") as f:
            terraform_template = f.read()
        terraform_config = terraform_template.format(
            region=self.region,
            ami_id=self.config.aws.ami_mapping[self.region],
            instance_type=self.config.aws.instance_type,
            aws_access_key=self.config.aws.access_key,
            aws_secret_key=self.config.aws.secret_key,
        )
        with open(f"{self.terraform_dir}/main.tf", "w") as f:
            f.write(terraform_config)
        shutil.copy2("collect_exchange_stats.py", f"{self.terraform_dir}/")
        shutil.copy2("terraform", f"{self.terraform_dir}/")
        exchange_config = {
            "exchanges": self.config.exchanges.api_keys,
            "region": self.region,
        }
        with open(f"{self.terraform_dir}/exchange_config.json", "w") as f:
            json.dump(exchange_config, f)

    def execute_terraform(self, command: str) -> bool:
        """
        Execute terraform command in the region directory

        Args:
            command: Terraform command to execute

        Returns:
            bool: True if command succeeded, False otherwise
        """
        try:
            subprocess.run(
                f"./terraform {command}", shell=True, check=True, cwd=self.terraform_dir
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error executing Terraform command: {e}")
            return False

    def get_instance_ip(self) -> Optional[str]:
        """Get the IP address of the created instance"""
        try:
            result = subprocess.run(
                "./terraform output -json instance_ip",
                shell=True,
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
            )
            print(f"Terraform output stdout: {result.stdout}")
            print(f"Terraform output stderr: {result.stderr}")

            if result.returncode != 0:
                print(f"Terraform command failed with return code: {result.returncode}")
                return None
            if result.stdout.strip():
                return json.loads(result.stdout)
            else:
                print("No output received from terraform command")
                return None

        except subprocess.CalledProcessError as e:
            print(f"Error executing Terraform command: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing Terraform output: {e}")
            print(f"Raw output: {result.stdout}")
            return None

    def wait_for_results(self, hostname: str) -> bool:
        """Wait for results file on the EC2 instance"""
        return ssh_wait_for_file(
            hostname=hostname,
            username=self.config.aws.ssh_username,
            private_key_path=self.config.aws.private_key_path,
            remote_path="/tmp",
            filename="exchange_stats.json",
            timeout=300,
        )

    def copy_results(self, hostname: str) -> bool:
        """Copy results from EC2 to local machine"""
        print(f"Copying results from {hostname}...")
        try:
            key = paramiko.RSAKey.from_private_key_file("blog_id_rsa")
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                client.connect(
                    hostname=hostname, username="ubuntu", pkey=key, timeout=60
                )
                sftp = client.open_sftp()
                try:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    local_path = os.path.join(
                        self.config.output_dir,
                        f"results_{self.region}_{timestamp}.json",
                    )
                    print(f"Copying /tmp/exchange_stats.json to {local_path}")
                    sftp.get("/tmp/exchange_stats.json", local_path)
                    return True

                except Exception as e:
                    print(f"SFTP error: {e}")
                    return False

                finally:
                    sftp.close()

            except Exception as e:
                print(f"SSH connection error: {e}")
                return False

            finally:
                client.close()

        except Exception as e:
            print(f"Error in copy_results: {e}")
            return False

    def cleanup_resources(self) -> bool:
        """Clean up all AWS resources created for this region"""
        print(f"\nCleaning up resources in {self.region}...")
        try:
            if not self.execute_terraform("destroy -auto-approve"):
                print(f"Warning: Terraform destroy failed in {self.region}")
                return False
            try:
                shutil.rmtree(self.terraform_dir)
                print(f"Removed terraform directory: {self.terraform_dir}")
            except Exception as e:
                print(f"Warning: Failed to remove terraform directory: {e}")
            return True
        except Exception as e:
            print(f"Error during cleanup: {e}")
            return False


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Exchange Latency Testing Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only generate the analysis report from existing results",
    )
    return parser.parse_args()


def generate_report(output_dir: str) -> None:
    """Generate analysis report from results"""
    print("\nGenerating analysis report...")
    from results_processor import ResultsProcessor

    processor = ResultsProcessor(output_dir)
    processor.generate_report()
    print(f"Analysis report generated at {os.path.join(output_dir, 'analysis.html')}")


def main():
    args = parse_args()
    config = load_config("config.yaml")
    os.makedirs(config.output_dir, exist_ok=True)

    if args.report_only:
        generate_report(config.output_dir)
        return
    for region in config.aws.regions:
        print(f"\nProcessing region: {region}")
        deployment = RegionDeployment(config, region)
        success = False

        try:
            deployment.prepare_terraform_files()
            if not deployment.execute_terraform("init"):
                continue

            if not deployment.execute_terraform("apply -auto-approve"):
                continue
            instance_ip = deployment.get_instance_ip()
            if not instance_ip:
                print(f"Failed to get instance IP for region {region}")
                continue
            if deployment.wait_for_results(instance_ip):
                if deployment.copy_results(instance_ip):
                    success = True
                else:
                    print(f"Failed to copy results from {region}")
            else:
                print(f"Failed to get results from {region}")

        except Exception as e:
            print(f"Error processing region {region}: {e}")

        finally:
            if not deployment.cleanup_resources():
                print(f"Warning: Failed to clean up some resources in {region}")

            if not success:
                print(f"Failed to complete testing in {region}")
            else:
                print(f"Successfully completed testing in {region}")
        if region != config.aws.regions[-1]:
            print("Waiting 30 seconds before processing next region...")
            time.sleep(30)
    generate_report(config.output_dir)


if __name__ == "__main__":
    main()
