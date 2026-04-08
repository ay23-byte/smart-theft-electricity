# SmartTheft Design System - Developer Guide

## 🎨 Quick Reference Guide

### Available CSS Variables

```css
/* Colors */
--color-primary: #00D4FF        /* Main brand color */
--color-secondary: #FF006E      /* Accent color */
--color-bg: #0A0E27             /* Background */
--color-bg-alt: #151B33         /* Alternative background */
--color-text: #E5E7EB           /* Primary text */
--color-text-muted: #9CA3AF     /* Muted text */
--color-border: #374151         /* Border color */
--color-success: #2ED573        /* Success state */
--color-danger: #FF4757         /* Error state */
--color-warning: #FFDA77        /* Warning state */

/* Spacing (multiples of 4px) */
--spacing-xs: 0.25rem      /* 4px */
--spacing-sm: 0.5rem       /* 8px */
--spacing-md: 1rem         /* 16px */
--spacing-lg: 1.5rem       /* 24px */
--spacing-xl: 2rem         /* 32px */
--spacing-2xl: 3rem        /* 48px */

/* Border Radius */
--radius-sm: 0.375rem     /* 6px */
--radius-md: 0.5rem       /* 8px */
--radius-lg: 0.75rem      /* 12px */
--radius-xl: 1rem         /* 16px */

/* Shadows */
--shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05)
--shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1)
--shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.2)
--shadow-glow: 0 0 20px rgba(0, 212, 255, 0.3)

/* Transitions */
--transition: all 0.2s ease       /* Standard animation */
--transition-slow: all 0.3s ease  /* Slow animation */
```

---

## 🎨 Using Colors

### ✅ Correct Usage:

```css
/* Use CSS variables */
.card {
    background: var(--color-bg-alt);
    border: 1px solid var(--color-border);
    color: var(--color-text);
    border-radius: var(--radius-lg);
}

/* Status messages */
.success {
    color: var(--color-success);
    background: rgba(46, 213, 115, 0.1);
}

.error {
    color: var(--color-danger);
    background: rgba(255, 71, 87, 0.1);
}
```

### ❌ Avoid:

```css
/* Hard-coded colors */
.card {
    background: #151B33;
    color: #00FFFF;
}
```

---

## 📐 Using Spacing

### ✅ Correct Usage:

```css
/* Use spacing variables */
.button {
    padding: var(--spacing-md) var(--spacing-lg);
    margin-bottom: var(--spacing-lg);
}

.container {
    padding: var(--spacing-xl);
    gap: var(--spacing-md);
}
```

### ❌ Avoid:

```css
/* Random values */
.button {
    padding: 12px 22px;
    margin-bottom: 20px;
}
```

---

## 📝 Creating Buttons

### Standard Button:
```html
<button class="btn">Click Me</button>
<a href="/page" class="btn">Link Button</a>
```

```css
.btn {
    padding: var(--spacing-md) var(--spacing-lg);
    min-height: 44px;
    color: var(--color-primary);
    background: transparent;
    border: 2px solid var(--color-primary);
    border-radius: var(--radius-lg);
    cursor: pointer;
    transition: var(--transition-slow);
}

.btn:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-glow);
}

.btn:focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: 2px;
}
```

### Variant: Primary Button

```css
.btn.primary {
    background: var(--color-primary);
    color: var(--color-bg);
}

.btn.primary:hover {
    background: rgba(0, 212, 255, 0.9);
}
```

### Variant: Danger Button

```css
.btn.danger {
    border-color: var(--color-danger);
    color: var(--color-danger);
}

.btn.danger:hover {
    background: var(--color-danger);
    color: white;
}
```

---

## 📋 Form Elements

### Input Best Practices:

```html
<label for="email">Email Address</label>
<input 
    id="email" 
    type="email" 
    placeholder="you@example.com"
    aria-label="Email address input"
/>
```

```css
input {
    min-height: 44px;
    padding: var(--spacing-md) var(--spacing-lg);
    background: var(--color-bg-alt);
    border: 2px solid var(--color-border);
    color: var(--color-text);
    border-radius: var(--radius-lg);
    transition: var(--transition);
}

input:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.1);
}

input::placeholder {
    color: var(--color-text-muted);
}
```

---

## 📱 Responsive Design

### Breakpoints:

```css
/* Mobile: < 480px (no media query needed - base styles) */

/* Tablet: 480px - 768px */
@media (max-width: 768px) {
    /* Tablet styles */
}

/* Mobile: < 480px */
@media (max-width: 480px) {
    /* Mobile styles */
}
```

### Responsive Container:

```css
.container {
    width: min(90%, 1400px);
    margin: 0 auto;
}

/* Instead of: */
/* width: 90%;
   max-width: 1400px; */
```

### Responsive Typography:

```css
h1 {
    font-size: clamp(1.875rem, 5vw, 2.5rem);
}

/* Scales from 30px to 40px based on viewport */
```

---

## 🎯 Accessibility Checklist

### Always Include:

```html
<!-- 1. Semantic HTML -->
<header>
<main>
<nav>
<section>
<article>
<footer>

<!-- 2. Labels for inputs -->
<label for="city">City Name</label>
<input id="city" type="text" />

<!-- 3. ARIA labels -->
<button aria-label="Close menu">×</button>

<!-- 4. Alt text for images -->
<img src="map.png" alt="Live theft tracking map" />

<!-- 5. Role attributes -->
<div role="status" aria-live="polite"></div>
```

### Focus States Required:

```css
button:focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: 2px;
}

a:focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: 2px;
}

input:focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: 2px;
}
```

---

## 🚀 Common Patterns

### Card Component:

```html
<div class="card">
    <h3>Title</h3>
    <p>Description</p>
</div>
```

```css
.card {
    background: var(--color-bg-alt);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--spacing-lg);
    box-shadow: var(--shadow-md);
    transition: var(--transition-slow);
}

.card:hover {
    box-shadow: var(--shadow-lg);
    transform: translateY(-2px);
}
```

### Alert Component:

```html
<div class="alert alert-success">Success message</div>
<div class="alert alert-error">Error message</div>
```

```css
.alert {
    padding: var(--spacing-lg);
    border-radius: var(--radius-lg);
    border-left: 4px solid;
    margin-bottom: var(--spacing-lg);
}

.alert-success {
    background: rgba(46, 213, 115, 0.1);
    border-color: var(--color-success);
    color: var(--color-success);
}

.alert-error {
    background: rgba(255, 71, 87, 0.1);
    border-color: var(--color-danger);
    color: var(--color-danger);
}
```

### Badge Component:

```html
<span class="badge">New</span>
<span class="badge badge-success">Active</span>
```

```css
.badge {
    display: inline-block;
    padding: var(--spacing-xs) var(--spacing-sm);
    background: var(--color-bg-alt);
    color: var(--color-text);
    border-radius: var(--radius-md);
    font-size: 0.85rem;
    font-weight: 600;
}

.badge-success {
    background: rgba(46, 213, 115, 0.2);
    color: var(--color-success);
}
```

---

## 🔍 Testing Your Design

### Color Contrast:
Use WebAIM Contrast Checker:
https://webaim.org/resources/contrastchecker/

### Responsive Design:
Test at breakpoints:
- 320px (Mobile)
- 480px (Mobile Large)
- 768px (Tablet)
- 1024px (Desktop)

### Accessibility:
Use WAVE Browser Extension:
https://wave.webaim.org/

Use Lighthouse:
Chrome DevTools > Lighthouse > Accessibility

### Performance:
Check CSS file size
Use Chrome DevTools > Coverage

---

## 📦 File Structure

```
frontend/
├── assets/
│   ├── css/
│   │   └── style.css          ← All styles (variables defined here)
│   └── js/
│       ├── dashboard.js
│       ├── map.js
│       └── earth.js
├── index.html                 ← Home page
├── map.html                   ← Map view
└── earth.html                 ← 3D Earth view
```

---

## ✨ Tips & Tricks

### 1. Quick Dark/Light Mode:

Add at bottom of CSS:
```css
@media (prefers-color-scheme: light) {
    :root {
        --color-bg: #F9FAFB;
        --color-text: #1F2937;
        --color-border: #D1D5DB;
    }
}
```

### 2. Print Styles:

```css
@media print {
    body { background: white; color: black; }
    .btn { border: 1px solid black; }
}
```

### 3. Reduced Motion:

```css
@media (prefers-reduced-motion: reduce) {
    * {
        animation-duration: 0.01ms !important;
        transition-duration: 0.01ms !important;
    }
}
```

### 4. High Contrast Mode:

```css
@media (prefers-contrast: more) {
    body { border: 2px solid currentColor; }
}
```

---

## 🐛 Common Issues & Solutions

### Issue: Colors look different on mobile
**Solution:** Test on actual devices, check device color settings

### Issue: Buttons look too small on mobile
**Solution:** Ensure minimum 44x44px touch targets. Already set!

### Issue: Text is hard to read
**Solution:** Check contrast ratio with WAVE tool

### Issue: Focus states not visible
**Solution:** Always include `:focus-visible` styles

### Issue: Spacing looks off
**Solution:** Use CSS variables, maintain 8px grid

---

## 📚 External Resources

- Colors: https://color.adobe.com/
- Fonts: https://fonts.google.com/
- Icons: https://heroicons.com/
- Accessibility: https://www.a11y-101.com/
- Typography: https://typescale.com/

---

## ✅ Before Adding New Styles

1. ✅ Check if variable exists
2. ✅ Use CSS variables first
3. ✅ Check contrast ratio
4. ✅ Test on mobile
5. ✅ Verify focus states
6. ✅ Add to git commit
7. ✅ Document changes

