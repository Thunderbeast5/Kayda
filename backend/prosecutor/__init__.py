"""
Prosecutor Agent Package

A specialized agent for defending the State/Complainant in criminal cases.
Uses lexigraphbe's query understanding and selective retrieval pipeline.
"""

from .prosecutor import ProsecutorAgent, CrimeAnalysis, ProsecutorAnalysis

__all__ = ["ProsecutorAgent", "CrimeAnalysis", "ProsecutorAnalysis"]
