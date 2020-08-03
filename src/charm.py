#!/usr/bin/env python3

import sys

sys.path.append("lib")

import logging
import base64

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    WaitingStatus,
    ModelError,
)

logger = logging.getLogger(__name__)


class PlexCharm(CharmBase):
    state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        self.state.set_default(spec=None)

        # Register all of the events we want to observe
        self.framework.observe(self.on.config_changed, self.on_config_changed)
        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.upgrade_charm, self.on_upgrade_charm)

    def _apply_spec(self):
        unit = self.framework.model.unit
        if not unit.is_leader():
            unit.status = ActiveStatus()
            return
        new_spec = self.make_pod_spec()
        if new_spec == self.state.spec:
            unit.status = ActiveStatus()
            return

        self.framework.model.pod.set_spec(new_spec)
        self.state.spec = new_spec
        unit.status = ActiveStatus()

    def make_pod_spec(self):
        config = self.framework.model.config
        
        ports = [
            {"name": "dlna", "containerPort": config["dlna-port"], "protocol": "TCP"},
            {"name": "http", "containerPort": config["port"], "protocol": "TCP"},
        ]

        spec = {
            "containers": [
                {
                    "name": self.framework.model.app.name,
                    "image": config["image"],
                    "ports": ports,
                    "config": {
                        "PLEX_CLAIM": config["claim"],
                        "ALLOWED_NETWORKS": config["allowed-networks"],
                        "ADVERTISE_IP": config["advertise-ip"],
                        "TZ": config["timezone"],
                    },
                }
            ],
        }

        return spec

    def on_config_changed(self, event):
        """Handle changes in configuration"""
        self._apply_spec()

    def on_start(self, event):
        """Called when the charm is being installed"""
        self._apply_spec()

    def on_upgrade_charm(self, event):
        """Upgrade the charm."""
        unit = self.model.unit
        unit.status = MaintenanceStatus("Upgrading charm")


if __name__ == "__main__":
    main(PlexCharm)

