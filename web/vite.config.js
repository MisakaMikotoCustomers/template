import { defineConfig } from 'vite'

export default defineConfig({
  // 构建输出目录
  build: {
    outDir: 'dist',
    // 资源文件名包含 hash，自动实现缓存 busting
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  // 将 BUILD_TAG 暴露给前端代码（通过 import.meta.env.VITE_BUILD_TAG 访问）
  define: {
    __BUILD_TAG__: JSON.stringify(process.env.VITE_BUILD_TAG || 'dev'),
  },
})
