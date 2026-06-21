# Examples

## Example 1: Long-Form Writing

### User Request

`寫一篇一千字的繁中文章，主題是為什麼事件驅動架構適合遊戲後端。`

### Delegation Shape

- Goal: produce a 1000-word Traditional Chinese article
- Constraints: no English output, avoid marketing fluff, include concrete examples
- Deliverables: markdown draft
- Acceptance checks: 900 to 1100 words, 3 concrete examples, readable structure

### Codex Review

- count approximate length
- scan for repeated filler
- confirm the examples are actually specific

## Example 2: Narrow Code Change

### User Request

`修掉登入表單空白 email 也能送出的 bug，順便補測試。`

### Delegation Shape

- Goal: reject blank email and add regression coverage
- Context: target form component, validation function, related tests
- Constraints: no unrelated refactor
- Deliverables: patch plus test evidence
- Acceptance checks: new test fails before fix and passes after fix

### Codex Review

- inspect diff scope
- verify validation behavior
- check test evidence

## Example 3: Refactor

### User Request

`把這個 500 行 utility 檔拆乾淨，但不要改行為。`

### Delegation Shape

- Goal: split one large file into smaller units without behavior change
- Constraints: preserve public API, preserve tests, no feature work
- Deliverables: patch and migration notes
- Acceptance checks: existing tests still pass, exports unchanged

### Codex Review

- inspect public surface
- verify test results
- scan for hidden behavior changes

## Example 4: Research Summary

### User Request

`幫我整理目前三種 2D pathfinding 實作方案的取捨。`

### Delegation Shape

- Goal: compare three implementation approaches
- Constraints: concise, decision-oriented, name trade-offs clearly
- Deliverables: comparison memo
- Acceptance checks: each option includes strengths, weaknesses, and suitable use cases

### Codex Review

- check whether the comparison is balanced
- remove unsupported certainty
- tighten any vague recommendations
