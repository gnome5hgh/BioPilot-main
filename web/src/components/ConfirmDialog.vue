<template>
  <div v-if="confirmState.open" class="confirm-mask" @click.self="settleConfirm(false)">
    <div class="confirm-card" role="alertdialog" aria-modal="true">
      <div class="confirm-title">{{ confirmState.title }}</div>
      <div class="confirm-message">{{ confirmState.message }}</div>
      <div v-if="confirmState.detail" class="confirm-detail">{{ confirmState.detail }}</div>
      <div class="confirm-actions">
        <button class="btn" @click="settleConfirm(false)">{{ confirmState.cancelText }}</button>
        <button class="btn" :class="confirmState.danger ? 'btn-danger' : 'btn-primary'"
                @click="settleConfirm(true)">{{ confirmState.confirmText }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { confirmState, settleConfirm } from '../utils/confirm'
</script>

<style scoped>
.confirm-mask {
  position: fixed;
  inset: 0;
  background: rgba(20, 24, 34, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 90;
  padding: 24px;
}

.confirm-card {
  width: min(460px, 100%);
  background: #fff;
  border-radius: 14px;
  padding: 22px;
  box-shadow: 0 16px 48px rgba(20, 24, 34, 0.2);
}

.confirm-title { font-size: 15px; font-weight: 700; margin-bottom: 8px; }
.confirm-message { color: #4a5160; line-height: 1.7; }
.confirm-detail {
  margin-top: 10px;
  background: #f8f9fc;
  border-radius: 8px;
  padding: 10px 12px;
  color: #818999;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}
.confirm-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
</style>
