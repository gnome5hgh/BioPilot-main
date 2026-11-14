<template>
  <div class="app">
    <AppSidebar />
    <main class="main"><router-view /></main>
  </div>
</template>

<script setup>
import AppSidebar from '../components/AppSidebar.vue'
</script>

<style scoped>
.app {
  display: flex;
  height: 100vh;
  min-width: 960px;
  overflow: hidden;
}
.main {
  flex: 1;
  min-width: 0;
  background: #fff;
  overflow: auto;
}
</style>
