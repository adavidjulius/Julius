
// I Want Ui — Julius Build Generated App
// Features: Core functionality as described, Responsive layout, Data persistence

const STORAGE_KEY = 'i-want-ui-todos';

// ── State ───────────────────────────────────────────────────────────
let todos = loadTodos();
let filter = 'all'; // 'all' | 'active' | 'done'

function loadTodos() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveTodos() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(todos));
}

function addTodo(text) {
  const trimmed = text.trim();
  if (!trimmed) return false;
  todos.unshift({ id: Date.now().toString(), text: trimmed, done: false, createdAt: new Date().toISOString() });
  saveTodos();
  render();
  return true;
}

function toggleTodo(id) {
  const todo = todos.find(t => t.id === id);
  if (todo) {
    todo.done = !todo.done;
    saveTodos();
    render();
  }
}

function deleteTodo(id) {
  todos = todos.filter(t => t.id !== id);
  saveTodos();
  render();
}

function clearCompleted() {
  todos = todos.filter(t => !t.done);
  saveTodos();
  render();
}

function filteredTodos() {
  switch (filter) {
    case 'active': return todos.filter(t => !t.done);
    case 'done':   return todos.filter(t => t.done);
    default:       return todos;
  }
}

// ── Render ──────────────────────────────────────────────────────────
function render() {
  const app = document.getElementById('app');
  const total = todos.length;
  const doneCount = todos.filter(t => t.done).length;
  const activeCount = total - doneCount;
  const visible = filteredTodos();
  const hasCompleted = doneCount > 0;

  // Set app.innerHTML to `
  app.innerHTML = `
    <h1>✨ I Want Ui</h1>
    <p class="subtitle">i want to build a ui for the ai agent named Julius</p>

    <div class="input-row">
      <input
        id="todo-input"
        type="text"
        placeholder="What needs to be done?"
        autocomplete="off"
        data-testid="todo-input"
      />
      <button id="add-btn" data-testid="add-btn">Add</button>
    </div>

    <div class="stats-row">
      <div class="stat">Total <span>${total}</span></div>
      <div class="stat">Active <span id="active-count">${activeCount}</span></div>
      <div class="stat">Done <span>${doneCount}</span></div>
    </div>

    <div class="filters">
      <button class="filter-btn ${filter === 'all' ? 'active' : ''}" data-filter="all">All</button>
      <button class="filter-btn ${filter === 'active' ? 'active' : ''}" data-filter="active">Active</button>
      <button class="filter-btn ${filter === 'done' ? 'active' : ''}" data-filter="done">Done</button>
    </div>

    <div class="todo-list" id="todo-list" data-testid="todo-list">
      ${visible.length === 0 ? `
        <div class="empty-state">
          <div class="emoji">🎉</div>
          <div>${filter === 'done' ? 'No completed tasks yet.' : filter === 'active' ? 'All tasks done!' : 'Add your first task above.'}</div>
        </div>
      ` : visible.map(todo => `
        <div class="todo-item ${todo.done ? 'done' : ''}" data-id="${todo.id}" data-testid="todo-item">
          <button class="todo-check ${todo.done ? 'done' : ''}" data-toggle="${todo.id}" data-testid="todo-check">
            <span class="checkmark">✓</span>
          </button>
          <span class="todo-text" data-testid="todo-text">${escapeHtml(todo.text)}</span>
          <button class="delete-btn" data-delete="${todo.id}" data-testid="delete-btn" title="Delete">✕</button>
        </div>
      `).join('')}
    </div>

    ${hasCompleted ? `<button class="clear-btn" id="clear-btn" data-testid="clear-btn">Clear completed (${doneCount})</button>` : ''}
  `;

  // ── Event bindings ────────────────────────────────────────────────
  const input = document.getElementById('todo-input');
  // Define constant addBtn set to document.getElementById('add-btn');
  const addBtn = document.getElementById('add-btn');

  // Execute statement: addBtn.addEventListener('click', () => {
  addBtn.addEventListener('click', () => {
    // Check condition: addTodo(input.value)
    if (addTodo(input.value)) input.value = '';
  });

  // Execute statement: input.addEventListener('keydown', e => {
  input.addEventListener('keydown', e => {
    // Check condition: e.key === 'Enter'
    if (e.key === 'Enter') {
      // Check condition: addTodo(input.value)
      if (addTodo(input.value)) input.value = '';
    }
  });

  // Execute statement: document.querySelectorAll('[data-toggle]').forEach(btn => {
  document.querySelectorAll('[data-toggle]').forEach(btn => {
    // Execute statement: btn.addEventListener('click', () => toggleTodo(btn.dataset.toggle));
    btn.addEventListener('click', () => toggleTodo(btn.dataset.toggle));
  });

  // Execute statement: document.querySelectorAll('[data-delete]').forEach(btn => {
  document.querySelectorAll('[data-delete]').forEach(btn => {
    // Execute statement: btn.addEventListener('click', () => deleteTodo(btn.dataset.delete));
    btn.addEventListener('click', () => deleteTodo(btn.dataset.delete));
  });

  // Execute statement: document.querySelectorAll('.filter-btn').forEach(btn => {
  document.querySelectorAll('.filter-btn').forEach(btn => {
    // Execute statement: btn.addEventListener('click', () => {
    btn.addEventListener('click', () => {
      // Set filter to btn.dataset.filter;
      filter = btn.dataset.filter;
      // Execute statement: render();
      render();
    });
  });

  // Define constant clearBtn set to document.getElementById('clear-btn');
  const clearBtn = document.getElementById('clear-btn');
  // Check condition: clearBtn) clearBtn.addEventListener('click', clearCompleted
  if (clearBtn) clearBtn.addEventListener('click', clearCompleted);
}

// Define function escapeHtml(text)
function escapeHtml(text) {
  // Return value text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); to caller
  return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Init ─────────────────────────────────────────────────────────────
render();
