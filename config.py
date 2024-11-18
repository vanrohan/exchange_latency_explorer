from typing import Dict, List
from dataclasses import dataclass

@dataclass
class AWSConfig:
    regions: List[str] = None
    instance_type: str = "t2.micro"
    ami_mapping: Dict[str, str] = None
    ssh_username: str = "ubuntu"
    key_pair_name: str = None
    private_key_path: str = None
    access_key: str = None
    secret_key: str = None

@dataclass
class ExchangeConfig:
    api_keys: Dict[str, Dict[str, str]]

@dataclass
class Config:
    aws: AWSConfig
    exchanges: ExchangeConfig
    output_dir: str = "./results"

def load_config(config_file: str) -> Config:
    """Load configuration from YAML file"""
    import yaml
    
    with open(config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    
    aws_config = AWSConfig(
        regions=config_data['aws']['regions'],
        instance_type=config_data['aws'].get('instance_type', 't2.micro'),
        ami_mapping=config_data['aws']['ami_mapping'],
        key_pair_name=config_data['aws']['key_pair_name'],
        private_key_path=config_data['aws']['private_key_path'],
        access_key=config_data['aws']['access_key'],
        secret_key=config_data['aws']['secret_key']
    )
    
    exchange_config = ExchangeConfig(
        api_keys=config_data['exchanges']['api_keys']
    )
    
    return Config(
        aws=aws_config,
        exchanges=exchange_config,
        output_dir=config_data.get('output_dir', './results')
    ) 

def validate_config(config: Config) -> None:
    """Validate configuration values"""
    if not config.aws.regions:
        raise ValueError("No AWS regions specified")
    if not config.aws.ami_mapping:
        raise ValueError("No AMI mapping provided")