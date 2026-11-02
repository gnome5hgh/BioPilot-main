<template>
  <div class="toast-host" aria-live="polite">
    <div v-for="item in toastState.items" :key="item.id"
         class="toast" :class="item.type">
      {{ item.message }}
    </div>
  </div>
</template>

<script setup>
import { toastState } from '../utils/toast'
</script>

<style scoped>
.toast-host {
  position: fixed;
  top: 18px;
  right: 20px;
  z-index: 80;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast {
  max-width: 360px;
  background: #2f3033;
  color: #fff;
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.5;
  box-shadow: 0 8px 24px rgba(20, 24, 34, 0.18);
  animation: toast-in 0.18s ease-out;
}

.toast.error { background: #b42318; }
.toast.success { background: #0f766e; }

@keyframes toast-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
