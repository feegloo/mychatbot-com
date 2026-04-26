<script setup lang="ts">
const props = defineProps<{
    events: string[]
}>()
</script>

<template>
    <section class="card">
        <h2>EventSource messages</h2>
        <pre>{{ props.events.join("\n") }}</pre>
    </section>
</template>
