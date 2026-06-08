"""Consul service registration utilities."""
import logging
from urllib.parse import urlparse

import consul
import urllib3

# Suppress SSL warnings when verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app import config as cfg

logger = logging.getLogger(__name__)


def _parse_consul_url(base_url: str) -> tuple[str, int]:
    """Parse consul base URL to extract host and port."""
    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 8500)
    return host, port


def register_service() -> bool:
    """Register the service with Consul."""
    if not cfg.CONSUL_ENABLED:
        logger.debug("Consul registration disabled (CONSUL_ENABLED=false)")
        return False
    
    if not cfg.CONSUL_BASE_URL or not cfg.CONSUL_TOKEN:
        logger.warning("Consul registration disabled (CONSUL_BASE_URL or CONSUL_TOKEN not set)")
        return False
    
    try:
        host, port = _parse_consul_url(cfg.CONSUL_BASE_URL)
        client = consul.Consul(
            host=host,
            port=port,
            token=cfg.CONSUL_TOKEN,
            scheme="https",
            verify=False
        )
        
        service_id = cfg.CONSUL_SERVICE_ID
        service_name = cfg.CONSUL_SERVICE_NAME
        
        # Register the service
        client.agent.service.register(
            name=service_name,
            service_id=service_id,
            address=cfg.CONSUL_SERVICE_API_URL,
            port=cfg.CONSUL_SERVICE_API_PORT,
            tags=["nextflow-api"],
            check=consul.Check.http(
                f"http://{cfg.CONSUL_SERVICE_API_URL}:{cfg.CONSUL_SERVICE_API_PORT}/nextflow-api/health",
                interval="10s",
                timeout="5s"
            )
        )
        
        logger.info(f"Service registered with Consul: {service_id} ({service_name})")
        return True
        
    except Exception as e:
        logger.error(f"Failed to register service with Consul: {e}")
        return False


def deregister_service() -> bool:
    """Deregister the service from Consul."""
    if not cfg.CONSUL_ENABLED:
        return False
    
    if not cfg.CONSUL_BASE_URL or not cfg.CONSUL_TOKEN:
        return False
    
    try:
        host, port = _parse_consul_url(cfg.CONSUL_BASE_URL)
        client = consul.Consul(
            host=host,
            port=port,
            token=cfg.CONSUL_TOKEN,
            scheme="https",
            verify=False
        )
        
        service_id = cfg.CONSUL_SERVICE_ID
        client.agent.service.deregister(service_id)
        logger.info(f"Service deregistered from Consul: {service_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to deregister service from Consul: {e}")
        return False
