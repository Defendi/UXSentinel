"""Módulo de Crawling e Exploração Autônoma do UXSentinel (UXS-12)."""

from uxsentinel.crawler.crawler import (
    Crawler,
    CrawlIssue,
    CrawlNode,
    CrawlOptions,
    is_destructive_element,
    is_same_origin,
    normalize_url,
)
from uxsentinel.crawler.generator import ScenarioGenerator

__all__ = [
    "CrawlIssue",
    "CrawlNode",
    "CrawlOptions",
    "Crawler",
    "ScenarioGenerator",
    "is_destructive_element",
    "is_same_origin",
    "normalize_url",
]
