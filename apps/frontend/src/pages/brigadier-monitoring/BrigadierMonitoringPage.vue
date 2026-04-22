<template>
  <main class="page">
    <section class="hero">
      <p class="eyebrow">Flowcraft MVP</p>
      <h1>Экран мониторинга бригадира</h1>
      <p class="description">
        Здесь будет обзор активных сотрудников, текущих таймеров и состояния
        заказов.
      </p>
    </section>

    <section class="panel">
      <div class="panel-item">
        <span class="label">Сотрудники в работе</span>
        <strong>0</strong>
      </div>
      <div class="panel-item">
        <span class="label">Простои</span>
        <strong>0</strong>
      </div>
      <div class="panel-item">
        <span class="label">Активные заказы</span>
        <strong>0</strong>
      </div>
    </section>
  </main>
</template>

<style scoped>
.page {
  padding: 32px;
}

.hero {
  max-width: 720px;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7d5d2e;
}

h1 {
  margin: 0 0 12px;
  font-size: clamp(2rem, 5vw, 3.25rem);
  line-height: 1.05;
}

.description {
  margin: 0;
  max-width: 54ch;
  font-size: 1.05rem;
}

.panel {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-top: 28px;
}

.panel-item {
  padding: 20px;
  border-radius: 18px;
  background: rgba(255, 250, 243, 0.92);
  border: 1px solid rgba(77, 57, 28, 0.14);
  box-shadow: 0 10px 30px rgba(73, 52, 18, 0.08);
}

.label {
  display: block;
  margin-bottom: 10px;
  color: #6f6558;
}

strong {
  font-size: 2rem;
}
</style>
