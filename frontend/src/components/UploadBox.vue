<script setup lang="ts">
import { ref } from "vue"

const props = defineProps<{
    status: string
}>()

const emit = defineEmits<{
    upload: [file: File]
}>()

const fileInput = ref<HTMLInputElement | null>(null)

/**
 * Emits selected PDF file to parent component.
 */
function handleSubmit(): void {
    const file = fileInput.value?.files?.[0]

    if (!file) {
        return
    }

    emit("upload", file)
}
</script>

<template>
    <section class="card">
        <h2>Upload test PDF</h2>
        <form @submit.prevent="handleSubmit">
            <input ref="fileInput" type="file" accept="application/pdf" required />
            <button type="submit">Upload</button>
        </form>
        <p>{{ props.status }}</p>
    </section>
</template>
