<template>
  <div class="home-hero">
    <img src="/logo.svg" alt="chatrag.app" class="home-logo" />
    <p class="home-subtitle">
      Upload securely 🔒 and chat with your Big PDFs and files.
      Your data is securely encrypted end-to-end. Let AI extract insights and tell you what's inside in the author's voices.<br /><br />
      Ask prompt to <strong> AI Agent chatbot</strong>, do research, use semantic search & RAG,
      synthesize speech 🔊, share answers<br />
      <span style="font-size: 12px; padding-top: 12px"
        >Generate image 🎨 book chapter 📖 poem 📜 diagnosis 🔬 quiz 🧠 quote 💡 PDF 📄 mermaid
        diagram 🧩 recipe 🍝 checklist ✅ and more!</span
      >
    </p>
  </div>
</template>

<style scoped>
.home-hero {
  text-align: center;
  margin-bottom: 32px;
  flex-shrink: 0;
}

.home-logo {
  height: 52px;
  width: auto;
  display: block;
  margin: -10px auto 16px;
  filter: drop-shadow(0 0 24px rgba(167, 139, 250, 0.3));
}

.home-subtitle {
  color: #64748b;
  margin: 0;
  font-size: 15px;
  line-height: 1.5;
}

@media (max-width: 768px) {
  .home-logo {
    height: 40px;
  }
}
</style>
