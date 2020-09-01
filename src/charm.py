#!/usr/bin/env python3

import logging

from urllib.parse import urlparse

from ops.charm import CharmBase

# from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    # MaintenanceStatus,
    # WaitingStatus,
    # ModelError,
)

logger = logging.getLogger(__name__)

REQUIRED_SETTINGS = ["plex_image_path"]

# We expect the plex container to use the
# default ports
HTTP_PORT = 32400
DLNA_PORT = 32469


class PlexCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        # Register all of the events we want to observe
        self.framework.observe(self.on.config_changed, self.configure_pod)
        self.framework.observe(self.on.start, self.configure_pod)
        self.framework.observe(self.on.upgrade_charm, self.configure_pod)

    def _check_settings(self):
        problems = []
        config = self.model.config

        for setting in REQUIRED_SETTINGS:
            if not config.get(setting):
                problem = f"missing config {setting}"
                problems.append(problem)

        return ";".join(problems)

    def _make_pod_image_details(self):
        config = self.model.config
        image_details = {
            "imagePath": config["plex_image_path"],
        }
        if config["plex_image_username"]:
            image_details.update(
                {
                    "username": config["plex_image_username"],
                    "password": config["plex_image_password"],
                }
            )
        return image_details

    def _make_pod_ports(self):
        return [
            {"name": "http", "containerPort": HTTP_PORT, "protocol": "TCP"},
            {"name": "dlna-tcp", "containerPort": DLNA_PORT, "protocol": "TCP"},
            {"name": "dlna-udp", "containerPort": DLNA_PORT, "protocol": "UDP"},
        ]

    def _make_pod_envconfig(self):
        config = self.model.config

        return {
            "PLEX_CLAIM": config["claim"],
            "ALLOWED_NETWORKS": config["allowed-networks"],
            "ADVERTISE_IP": config["advertise-ip"],
            "TZ": config["timezone"],
        }

    def _make_pod_ingress_resources(self):
        site_url = self.model.config["site_url"]

        if not site_url:
            return

        parsed = urlparse(site_url)

        if not parsed.scheme.startswith("http"):
            return

        max_file_size = self.model.config["max_file_size"]
        ingress_whitelist_source_range = self.model.config[
            "ingress_whitelist_source_range"
        ]

        annotations = {}
        annotations["nginx.ingress.kubernetes.io/proxy-body-size"] = f"{max_file_size}m"

        if ingress_whitelist_source_range:
            annotations[
                "nginx.ingress.kubernetes.io/whitelist-source-range"
            ] = ingress_whitelist_source_range

        ingress = {
            "name": "{}-ingress".format(self.app.name),
            "annotations": annotations,
            "spec": {
                "rules": [
                    {
                        "host": parsed.hostname,
                        "http": {
                            "paths": [
                                {
                                    "path": "/",
                                    "backend": {
                                        "serviceName": self.app.name,
                                        "servicePort": HTTP_PORT,
                                    },
                                }
                            ]
                        },
                    }
                ]
            },
        }

        if parsed.scheme == "https":
            ingress["spec"]["tls"] = [{"hosts": [parsed.hostname]}]
        else:
            ingress["annotations"]["nginx.ingress.kubernetes.io/ssl-redirect"] = "false"

        return [ingress]

    def configure_pod(self, event):
        # Continue only if the unit is the leader
        if not self.unit.is_leader():
            self.unit.status = ActiveStatus()
            return
        # Check problems in the settings
        problems = self._check_settings()
        if problems:
            self.unit.status = BlockedStatus(problems)
            return

        self.unit.status = BlockedStatus("Assembling pod spec")
        image_details = self._make_pod_image_details()
        ports = self._make_pod_ports()
        env_config = self._make_pod_envconfig()
        ingress_resources = self._make_pod_ingress_resources()

        pod_spec = {
            "version": 3,
            "containers": [
                {
                    "name": self.framework.model.app.name,
                    "imageDetails": image_details,
                    "ports": ports,
                    "envConfig": env_config,
                }
            ],
            "kubernetesResources": {"ingressResources": ingress_resources or [],},
        }
        self.model.pod.set_spec(pod_spec)
        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(PlexCharm)
