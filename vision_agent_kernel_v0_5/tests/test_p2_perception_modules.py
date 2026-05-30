"""Tests for P2 perception enhancement modules."""
from __future__ import annotations

import pytest
import numpy as np

from perception.damage_number_parser import DamageNumberParser, DamageColor
from perception.hp_ocr_reader import HPOcrReader
from perception.vlm_performance_monitor import VLMPerformanceMonitor
from perception.shield_type_detector import ShieldTypeDetector, ShieldType


class TestDamageNumberParser:
    def test_can_be_instantiated(self) -> None:
        parser = DamageNumberParser()
        assert parser is not None

    def test_damage_color_enum(self) -> None:
        assert DamageColor.WHITE is not None
        assert DamageColor.YELLOW is not None
        assert DamageColor.RED is not None


class TestHPOcrReader:
    def test_can_be_instantiated(self) -> None:
        reader = HPOcrReader()
        assert reader is not None


class TestVLMPerformanceMonitor:
    def test_can_be_instantiated(self) -> None:
        monitor = VLMPerformanceMonitor()
        assert monitor is not None

    def test_p95_threshold_default(self) -> None:
        monitor = VLMPerformanceMonitor()
        assert monitor._p95_threshold > 0


class TestShieldTypeDetector:
    def test_can_be_instantiated(self) -> None:
        detector = ShieldTypeDetector()
        assert detector is not None

    def test_shield_type_enum(self) -> None:
        assert ShieldType.GEO is not None
        assert ShieldType.CRYO is not None
        assert ShieldType.ELECTRO is not None