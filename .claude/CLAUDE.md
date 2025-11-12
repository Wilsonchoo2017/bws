# Coding and Testing Standards

## Coding Principles

### DRY (Don't Repeat Yourself)

- Eliminate code duplication by extracting common logic into reusable functions,
  components, or modules
- If you find yourself copying code, refactor it into a shared abstraction
- Apply DRY judiciously - premature abstraction can be worse than minor
  duplication

### SOLID Principles

#### Single Responsibility Principle (SRP)

- Each function, class, or module should have one clear purpose
- If a function does multiple unrelated things, split it into separate functions
- Name functions and modules based on their single responsibility

#### Open/Closed Principle

- Code should be open for extension but closed for modification
- Use composition, dependency injection, and interfaces to add new behavior
  without changing existing code

#### Liskov Substitution Principle

- Subtypes must be substitutable for their base types
- Derived implementations should honor the contract of their interfaces

#### Interface Segregation Principle

- Prefer small, focused interfaces over large, monolithic ones
- Don't force clients to depend on methods they don't use

#### Dependency Inversion Principle

- Depend on abstractions, not concretions
- High-level modules should not depend on low-level modules; both should depend
  on abstractions

### Additional Core Principles

#### KISS (Keep It Simple, Stupid)

- Prefer simple, straightforward solutions over clever or complex ones
- Write code that is easy to understand and maintain
- Avoid premature optimization

#### YAGNI (You Aren't Gonna Need It)

- Don't add functionality until it's actually needed
- Resist the urge to build features "just in case"
- Focus on current requirements, not hypothetical future ones

#### Pure Functions

- Prefer pure functions that:
  - Return the same output for the same input
  - Have no side effects
  - Don't mutate arguments or external state
- Pure functions are easier to test, reason about, and debug

#### Immutability

- Prefer immutable data structures
- Use spread operators, `Object.freeze()`, or immutable libraries
- Avoid mutating objects or arrays; create new instances instead

#### Separation of Concerns

- Separate business logic from presentation
- Keep data access separate from business rules
- Organize code into clear layers (e.g., routes, services, data access)

#### Composition Over Inheritance

- Favor composing small, focused functions/components over deep inheritance
  hierarchies
- Use functional composition and higher-order functions
- Inheritance should be reserved for true "is-a" relationships

### Code Quality

#### Naming

- Use descriptive, intention-revealing names
- Functions should be verbs, variables should be nouns
- Avoid abbreviations unless universally understood
- Be consistent with naming conventions

#### Functions

- Keep functions small and focused (ideally < 20 lines)
- Limit function parameters (max 3-4; use objects for more)
- Avoid boolean flags; split into separate functions instead
- Return early to reduce nesting

#### Error Handling

- Handle errors explicitly; don't ignore them
- Use custom error types for different error categories
- Provide meaningful error messages
- Fail fast and fail loud

## Testing Principles

### Test Behavior, Not Implementation

**DO:**

- Test what the code does (outputs, side effects, state changes)
- Test from the user's perspective
- Focus on public API and contracts
- Verify outcomes and observable behavior

**DON'T:**

- Test internal implementation details
- Assert on private methods or internal state
- Mock excessively or create brittle test doubles
- Tie tests to specific code structure

**Example:**

```typescript
// Good: Testing behavior
test("user can add item to cart", () => {
  const cart = new ShoppingCart();
  cart.addItem({ id: 1, name: "Widget", price: 10 });
  expect(cart.getTotalPrice()).toBe(10);
  expect(cart.getItemCount()).toBe(1);
});

// Bad: Testing implementation
test("addItem calls private _items.push", () => {
  const cart = new ShoppingCart();
  const spy = jest.spyOn(cart["_items"], "push"); // Testing internals
  cart.addItem({ id: 1, name: "Widget", price: 10 });
  expect(spy).toHaveBeenCalled(); // Brittle!
});
```

### Write Maintainable Tests

- **Readable**: Tests should read like documentation
- **Independent**: Each test should run in isolation
- **Fast**: Tests should execute quickly
- **Repeatable**: Same results every time
- **Self-validating**: Clear pass/fail with no manual verification

### Test Structure

Use the **Arrange-Act-Assert (AAA)** pattern:

```typescript
test("description of behavior", () => {
  // Arrange: Set up test data and conditions
  const input = createTestData();

  // Act: Execute the behavior being tested
  const result = performAction(input);

  // Assert: Verify the outcome
  expect(result).toBe(expected);
});
```

### Test Naming

- Use descriptive test names that explain the behavior
- Format: `should [expected behavior] when [condition]`
- Examples:
  - `should return empty array when no items match filter`
  - `should throw error when input is invalid`
  - `should update user profile when valid data is provided`

### What to Test

**High Priority:**

- Critical business logic
- Edge cases and boundary conditions
- Error handling paths
- Public API contracts

**Lower Priority:**

- Simple getters/setters
- Framework code
- Third-party library internals
- Configuration files

### Test Independence

- Each test should set up its own data
- Don't rely on test execution order
- Clean up after tests (use `afterEach`, `beforeEach`)
- Avoid shared mutable state between tests

### Mocking Guidelines

**When to Mock:**

- External dependencies (APIs, databases, file systems)
- Slow operations
- Non-deterministic behavior (random, dates, timers)

**When NOT to Mock:**

- Your own code being tested
- Simple pure functions
- Most internal collaborators

**Principle:** Mock at the boundaries, not internally

### Test Coverage

- Aim for high coverage of critical paths, not 100% coverage
- Focus on meaningful tests, not coverage metrics
- Quality over quantity
- Uncovered code should be intentional, not accidental

### Avoid Brittle Tests

**Sources of Brittleness:**

- Testing implementation details
- Over-mocking internal collaborators
- Hardcoded test data that's fragile
- Tests coupled to exact string matching
- Snapshot tests without clear purpose

**Solutions:**

- Test through public interfaces
- Use minimal, meaningful mocking
- Generate test data with factories
- Use flexible assertions
- Review snapshots carefully

### Test-Driven Development (TDD)

When appropriate, follow the Red-Green-Refactor cycle:

1. **Red**: Write a failing test
2. **Green**: Write minimal code to make it pass
3. **Refactor**: Improve the code while keeping tests green

Benefits:

- Tests guide design
- Better test coverage
- Clearer requirements
- Confidence in refactoring

## General Guidelines

- **Performance**: Optimize for readability first, performance second (measure
  before optimizing)
- **Security**: Validate inputs, sanitize outputs, use parameterized queries,
  avoid hardcoded secrets
- **Documentation**: Code should be self-documenting; add comments only when
  necessary to explain "why"
- **Consistency**: Follow existing patterns in the codebase
- **Refactoring**: Leave code better than you found it (Boy Scout Rule)
