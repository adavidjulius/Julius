PROJECT KNOWLEDGE BASE (PKB) IMPLEMENTATION SPECIFICATION
Objective
You are an expert software architect, compiler engineer, distributed systems engineer, database engineer, and AI agent researcher.
Your objective is to design and implement a world-class Project Knowledge Base (PKB) that completely replaces expensive LLM repository searching.
The PKB must become the primary intelligence layer of the coding agent.
The LLM must never search repositories directly unless absolutely necessary.
Instead, every repository understanding task must be answered through the PKB.
The architecture must support repositories containing millions of lines of code while maintaining low latency and minimal token usage.
Design Principles 
The implementation must satisfy the following principles.
Repository understanding is deterministic.
LLM reasoning is expensive.
Parsing is cheap.
Indexing is incremental.
Retrieval is hierarchical.
Context is minimized.
Every expensive operation must be cached.
Every retrieved item must have provenance.
Every index must be incrementally updated.
High-Level Architecture
Repository
      │
      ▼
Repository Watcher
      │
      ▼
Change Detector
      │
      ▼
Parser Layer
(Tree-sitter)
      │
      ▼
Knowledge Extraction Pipeline
      │
      ├──────── Symbol Extraction
      ├──────── AST Extraction
      ├──────── Import Graph
      ├──────── Export Graph
      ├──────── Call Graph
      ├──────── Type Graph
      ├──────── Dependency Graph
      ├──────── File Metadata
      ├──────── Documentation
      ├──────── Git Metadata
      ├──────── Test Metadata
      ├──────── Build Metadata
      └──────── Runtime Metadata
               │
               ▼
Project Knowledge Base
               │
               ▼
Retrieval Engine
               │
               ▼
Context Optimizer
               │
               ▼
LLM
Layer 1 — Repository Monitor
Implement a filesystem watcher.
Monitor
new files
modified files
deleted files
renamed files
Do NOT rebuild the repository.
Only changed files may be re-indexed.
Maintain a processing queue.
Debounce rapid changes.
Support parallel indexing.
Layer 2 — Language Parser
Use Tree-sitter.
Never use an LLM for parsing.
Support at minimum
Python
TypeScript
JavaScript
Rust
Go
Java
C
C++
Swift
Kotlin
Expandable parser interface.
Layer 3 — Symbol Extraction
Extract
Functions
Methods
Classes
Interfaces
Structs
Enums
Namespaces
Modules
Variables
Constants
Macros
Decorators
Annotations
Generics
Return types
Parameter types
Visibility
Inheritance
Traits
Protocols
Each symbol receives a globally unique identifier.
Example
Symbol ID

auth.login.authenticateUser
Layer 4 — AST Database
Store the entire Abstract Syntax Tree.
Each node contains
Node ID
Parent
Children
Language
Node Type
Location
File
Line
Column
Scope
Every AST node must be queryable.
Layer 5 — Call Graph
Construct a directed graph.
login()

↓

verifyPassword()

↓

generateJWT()

↓

cache.store()
Store
caller
callee
frequency
location
indirect calls
recursive calls
async calls
Layer 6 — Import Graph
Build import relationships.
App

↓

Router

↓

Auth

↓

JWT

↓

Crypto
Support reverse lookup.
Layer 7 — Dependency Graph
Build package dependency graph.
Support
external packages
internal modules
dynamic imports
lazy loading
plugins
Layer 8 — Symbol Relationship Graph
Store
implements
inherits
extends
uses
creates
owns
contains
references
imports
exports
overrides
calls
returns
accepts
Every relationship must be traversable.
Layer 9 — File Database
Store
file path
language
size
checksum
last modification
creation date
owner
encoding
generated/manual
Layer 10 — Documentation Index
Extract
comments
docstrings
README
Markdown
API docs
Wiki
Associate documentation with symbols.
Layer 11 — Git Intelligence
Store
commit history
author
last modifier
branch
merge history
blame information
diff history
Allow queries like
"Who last modified this function?"
without invoking an LLM.
Layer 12 — Runtime Knowledge
Store
build errors
compiler diagnostics
stack traces
test failures
coverage
performance traces
profiling
runtime logs
execution traces
link runtime information to symbols.
Layer 13 — Test Knowledge
Map
test
↓
function
↓
class
↓
module
Agent must answer
"What tests cover this method?"
instantly.
Layer 14 — Semantic Embeddings
Generate embeddings for
functions
classes
documentation
files
Store inside a local vector database.
Support
semantic search
hybrid search
reranking
Layer 15 — Retrieval Engine
The retrieval engine must perform multi-stage retrieval.
Stage 1
Intent detection
↓
Stage 2
Symbol lookup
↓
Stage 3
Call graph expansion
↓
Stage 4
Dependency expansion
↓
Stage 5
Documentation retrieval
↓
Stage 6
Runtime retrieval
↓
Stage 7
Ranking
↓
Stage 8
Context assembly
Never retrieve entire repositories.
Retrieve only necessary context.
Layer 16 — Context Optimizer
Remove
duplicates
unused imports
irrelevant code
generated code
vendor folders
Compress
AST
documentation
comments
Only send the minimum context.
Layer 17 — Memory System
Persistent memory.
Remember
frequently accessed files
recent searches
recent symbols
recent edits
session history
Avoid rediscovering information.
Layer 18 — Incremental Indexing
When
auth/login.py
changes
Only update
auth/login.py
Do not rebuild the repository.
Update
AST
graphs
embeddings
symbol database
relationships
atomically.
Layer 19 — Query API
Expose APIs.
findSymbol()

findFile()

findCallers()

findCallees()

findTests()

findDocumentation()

findImplementations()

findReferences()

findDependencies()

semanticSearch()

graphSearch()

buildContext()

getRuntimeErrors()

getRecentChanges()

findAffectedFiles()
All APIs must return structured objects.
Layer 20 — LLM Integration
The LLM must NEVER search.
Workflow
User Request

↓

Intent Analyzer

↓

Knowledge Base Query

↓

Retrieve Symbols

↓

Expand Relationships

↓

Compress Context

↓

LLM

↓

Response
The LLM receives only optimized context.
Storage
Use SQLite (or PostgreSQL for large deployments) for structured metadata.
Use a graph database abstraction (or graph tables) for relationships.
Use a local vector database for embeddings.
Implement repositories for each storage backend to allow future replacement.
Performance Goals
Initial indexing:
Maximize throughput with parallel workers.
Incremental updates:
Target sub-second updates for typical file changes.
Symbol lookup:
O(1) or logarithmic time.
Graph traversal:
Low-latency for common dependency depths.
Semantic search:
Top-k retrieval with reranking.
Context assembly:
Produce minimal context within a few hundred milliseconds on medium-sized repositories.
The system should be designed to scale to repositories with millions of lines of code.
Security
Never send repository data outside the local machine unless explicitly requested.
Redact secrets.
Detect
API keys
passwords
tokens
private certificates
private keys
Never expose them to the LLM.
Extensibility
Everything must be plugin-based.
Parser plugins
Language plugins
Graph plugins
Embedding plugins
Storage plugins
Retrieval plugins
Ranking plugins
Memory plugins
Runtime plugins
No module should depend directly on implementation details of another.
Deliverables
Implement:
Complete architecture
Modular codebase
Clear interfaces
Incremental indexing pipeline
Query engine
Graph engine
Retrieval engine
Context optimizer
Persistent storage
Tests
Benchmarks
Documentation
Diagrams
Profiling hooks
Configuration system
Logging
Error recovery
The resulting system should function as a compiler-grade repository intelligence platform that allows an AI coding agent to understand large codebases with minimal token usage, low latency, deterministic retrieval, and a persistent, evolving understanding of the project's structure and behavior.