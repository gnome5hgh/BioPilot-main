<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="brand">BioPilot</div>
      <div class="sub">实验室生信科研智能平台</div>
      <input v-model="userName" placeholder="用户名" @keyup.enter="submit" />
      <input v-model="password" type="password" placeholder="密码" @keyup.enter="submit" />
      <input v-model="nickName" placeholder="昵称（注册时填写，选填）" v-if="mode === 'register'" />
      <button class="primary" @click="submit">{{ mode === 'login' ? '登录' : '注册并登录' }}</button>
      <a class="switch" @click="toggle">{{ mode === 'login' ? '没有账号？注册' : '已有账号？登录' }}</a>
      <p class="error" v-if="error">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../api/auth'

const auth = useAuthStore()
const router = useRouter()
const mode = ref('login')
const userName = ref('')
const password = ref('')
const nickName = ref('')
const error = ref('')

function toggle() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  error.value = ''
}

async function submit() {
  error.value = ''
  try {
    if (mode.value === 'login') {
      await auth.login(userName.value, password.value)
    } else {
      await auth.register(userName.value, password.value, nickName.value)
      await auth.login(userName.value, password.value)
    }
    router.push('/')
  } catch (e) {
    error.value = e.message
  }
}
</script>

<style scoped>
.login-wrap { height: 100vh; display: flex; align-items: center; justify-content: center; background: #f8f9fc; }
.login-card { width: 340px; background: #fff; border: 1px solid #e6e9ed; border-radius: 14px; padding: 32px; display: flex; flex-direction: column; gap: 12px; }
.brand { font-size: 24px; font-weight: 700; color: #2f3033; }
.sub { font-size: 13px; color: #818999; margin-bottom: 12px; }
input { border: 1px solid #e6e9ed; border-radius: 8px; height: 38px; padding: 0 12px; font-size: 14px; }
button.primary { background: #2ec5b1; color: #fff; border: none; border-radius: 8px; height: 40px; font-size: 15px; cursor: pointer; }
button.primary:hover { background: #26b39f; }
.switch { font-size: 13px; color: #2ec5b1; cursor: pointer; text-align: center; }
.error { color: #e7000b; font-size: 13px; margin: 0; }
</style>
