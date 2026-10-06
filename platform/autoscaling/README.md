# Автоматическое масштабирование worker-нод

## Стенд

- Управляющий кластер: Kind campus-management, Kubernetes 1.37.0.
- Cluster API и Docker provider: 1.14.2.
- Рабочий кластер: campus-autoscale, Kubernetes 1.36.4.
- CNI рабочего кластера: Cilium 1.20.1.
- Cluster Autoscaler: 1.36.1.
- Группа worker-нод: минимум 1, максимум 2.

Основная платформа работает в отдельном Minikube-кластере campus.
На время теста он остановлен для освобождения памяти.

## Принцип работы

Cluster Autoscaler наблюдает за Pod рабочего кластера и изменяет
размер MachineDeployment в управляющем кластере. Cluster API
Docker provider создаёт и удаляет реальные контейнеры worker-нод.

В Cluster topology фиксированное поле replicas для worker-группы
удалено. Аннотации задают минимальный и максимальный размер группы.

## Проверка 2026-10-06

1. Исходное состояние: один control-plane и один worker, оба Ready.
2. Создан Deployment autoscale-test с двумя Pod и обязательным
   размещением на разных узлах через podAntiAffinity.
3. Один Pod запустился, второй остался Pending.
4. Cluster Autoscaler автоматически увеличил worker-группу до двух.
5. Второй worker стал Ready; оба Pod запустились на разных worker.
6. После удаления Deployment автоскейлер уменьшил группу до одного.
7. В логах подтверждено событие ScaleDown: node removed with drain.
8. Итог: один control-plane и один worker, MachineDeployment 1/1.

Подтверждён цикл автоматического масштабирования: 1 → 2 → 1 worker.
Автоскейлер удалил исходный worker, оставив добавленный — это допустимо.

## Файлы

- kind-management.yaml — управляющий кластер с Docker socket.
- workload-cluster.yaml — шаблон рабочего кластера.
- cilium-values.yaml — настройки CNI.
- worker-group-patch.json — диапазон worker-группы и передача
  управления числом реплик автоскейлеру.
- compose.yaml — запуск Cluster Autoscaler.
- test-workload.yaml — тест потребности в дополнительном узле.

После применения workload-cluster.yaml обязательно применяется
worker-group-patch.json. Повторное применение исходного шаблона
может вернуть фиксированное replicas: 1.

## Подключения

Kubeconfig хранятся вне репозитория:

- %USERPROFILE%\k8s-tools\autoscaler-management.yaml
- %USERPROFILE%\k8s-tools\autoscaler-workload.yaml

Они содержат административные учётные данные и не коммитятся.
После пересоздания кластеров kubeconfig нужно экспортировать заново.

Для первоначальной установки Cluster API нужно включить
CLUSTER_TOPOLOGY=true перед clusterctl init --infrastructure docker.

Перед запуском через Compose нужно удалить одноимённый контейнер,
если он ранее создан командой docker run.

## Ограничения

Docker provider предназначен для локальных тестов.
Все узлы используют ресурсы одного компьютера.

Тест проверяет масштабирование из-за невозможности разместить Pod
с заданными ограничениями. Он не измеряет производительность
CampusReserve под CPU-нагрузкой.

Автоскейлинг продемонстрирован в отдельном рабочем кластере;
основной Minikube-кластер campus автоматически не масштабируется.