import trimesh
import numpy as np
from OpenGL.GL import *
import os

class GLTFLoader:
    def __init__(self, glb_filepath):
        self.display_lists = []
        self.texture_ids = []
        
        print(f"\n📦 Загрузка сцены из {glb_filepath}...")
        scene = trimesh.load(glb_filepath, force='scene')
        meshes = list(scene.dump())
        print(f"🌳 Найдено {len(meshes)} объектов.\n")
        
        for i, mesh in enumerate(meshes):
            name = getattr(mesh, 'metadata', {}).get('name', f'Object_{i}')
            dl = self._compile_mesh_to_gpu(mesh, scene, name)
            if dl is not None:
                self.display_lists.append(dl)
                
        print(f"\n✅ Сцена загружена ({len(self.display_lists)} объектов).")

    def _get_color_for_material(self, material_name, mesh_name):
        """Определяет цвет объекта по имени материала."""
        name_lower = material_name.lower()
        
        # Листва - зелёный
        if 'material.001' in name_lower or 'leaf' in name_lower or 'foliage' in name_lower:
            return (0.2, 0.6, 0.2, 1.0)  # Зелёный
        
        # Ствол - коричневый
        elif 'material.002' in name_lower or 'trunk' in name_lower or 'wood' in name_lower:
            return (0.4, 0.25, 0.1, 1.0)  # Коричневый
        
        # Трава/земля - тёмно-зелёный
        elif 'grass' in name_lower or 'ground' in name_lower:
            return (0.15, 0.35, 0.1, 1.0)  # Тёмно-зелёный
        
        # Всё остальное - серый
        else:
            return (0.5, 0.5, 0.5, 1.0)  # Серый

    def _compile_mesh_to_gpu(self, mesh, scene, mesh_name):
        if not hasattr(mesh, 'vertices') or len(mesh.vertices) == 0:
            return None
            
        # Получаем имя материала и определяем цвет
        mat = getattr(mesh.visual, 'material', None)
        material_name = getattr(mat, 'name', 'Unknown') if mat else 'Unknown'
        color = self._get_color_for_material(material_name, mesh_name)
        
        # Компиляция в Display List
        dl = glGenLists(1)
        glNewList(dl, GL_COMPILE)
        
        # Отключаем текстуры, используем только цвета
        glDisable(GL_TEXTURE_2D)
        glColor4f(*color)
        
        normals = mesh.vertex_normals
        
        glBegin(GL_TRIANGLES)
        for face in mesh.faces:
            for idx in face:
                if normals is not None:
                    glNormal3f(*normals[idx])
                glVertex3f(*mesh.vertices[idx])
        glEnd()
        
        glEndList()
        return dl

    def draw(self):
        # Отключаем текстуры и отсечение задних граней
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_CULL_FACE)
        
        for dl in self.display_lists:
            glCallList(dl)
            
        glEnable(GL_CULL_FACE)

    def cleanup(self):
        for dl in self.display_lists:
            glDeleteLists(dl, 1)
        for tid in self.texture_ids:
            glDeleteTextures([tid])