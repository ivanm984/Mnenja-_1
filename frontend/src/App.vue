<template>
  <div class="container-shell">
    <hero-section />
    <div class="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <div class="flex flex-col gap-6">
        <upload-section class="surface-card" />
        <metadata-section class="surface-card" />
        <requirements-section class="surface-card" />
      </div>
      <sidebar-actions class="surface-card" />
    </div>
    <saved-sessions-modal />
  </div>
</template>

<script setup lang="ts">
import HeroSection from './sections/HeroSection.vue';
import UploadSection from './sections/UploadSection.vue';
import MetadataSection from './sections/MetadataSection.vue';
import RequirementsSection from './sections/RequirementsSection.vue';
import SidebarActions from './sections/SidebarActions.vue';
import SavedSessionsModal from './sections/SavedSessionsModal.vue';
</script>
