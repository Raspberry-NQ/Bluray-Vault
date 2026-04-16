# rs_code — Cauchy Reed-Solomon Erasure Code Library

基于 ICSI 技术报告 TR-95-048 的 Cauchy Reed-Solomon 纠删码 C 语言库。提供运行时可配置的前向纠错（FEC）编解码能力，所有编码/解码运算在有限域上仅使用 XOR 完成，具备较高的软件执行效率。

---

## 目录

1. [概述](#1-概述)
2. [理论基础](#2-理论基础)
3. [架构设计](#3-架构设计)
4. [构建](#4-构建)
5. [API 参考](#5-api-参考)
6. [使用示例](#6-使用示例)
7. [参数配置指南](#7-参数配置指南)
8. [数据布局](#8-数据布局)
9. [集成指南](#9-集成指南)
10. [测试](#10-测试)
11. [与原始代码的对比](#11-与原始代码的对比)
12. [局限性](#12-局限性)

---

## 1. 概述

本库实现了 Cauchy 构造的 Reed-Solomon 纠删码，核心特性如下：

| 特性 | 描述 |
|------|------|
| 算法 | Cauchy Reed-Solomon，基于 GF(2^w) |
| 编码运算 | 仅 XOR（无需有限域通用乘法） |
| 可配置域 | GF(2^1) ~ GF(2^15)，运行时指定 |
| 纠删能力 | 丢失不超过 rpackets 个包均可恢复 |
| 语言 | C11，提供 C++ `extern "C"` 兼容 |
| 构建系统 | CMake 3.20+ |

典型工作流：

```
原始消息 ──→ rs_encode() ──→ 编码包（消息包 + 冗余包）
                                     │
                               传输 / 存储（可能丢包）
                                     │
                               接收到的包（≥ mpackets 个）
                                     │
                             rs_decode() ──→ 恢复的原始消息
```

---

## 2. 理论基础

### 2.1 纠删码与 Reed-Solomon 码

纠删码（Erasure Code）将长度为 *k* 的消息编码为长度为 *n* 的码字（*n > k*），其中任意 *k* 个码字符号足以重建原始消息。Reed-Solomon（RS）码是最经典的纠删码，基于有限域（Galois Field）上的多项式运算。

经典 RS 编码使用 Vandermonde 矩阵，需要在有限域上执行通用乘法。**Cauchy RS** 用 Cauchy 矩阵替代 Vandermonde 矩阵，其关键优势在于：

- Cauchy 矩阵的任意子方阵必然可逆（保证可解码性）
- 在 GF(2^w) 上，Cauchy 矩阵的元素可以通过位运算（XOR）完成编码，无需查表乘法

### 2.2 本实现的具体方法

本实现取自 ICSI 技术报告 TR-95-048：

> "An XOR-Based Erasure-Resilient Coding Scheme"
> Johannes Bloemer, Malik Kalfane, Marek Karpinski, Richard Karp, Michael Luby, David Zuckerman

编码矩阵元素的构造方式为：

```
C[row][col] = GF(2^w) 上的元素 (row ⊕ col ⊕ COLBIT)
```

其中 `⊕` 为按位异或，`COLBIT = 2^(w-1)`。对矩阵元素做对数/指数表查表后，编码过程被分解为一系列 XOR 操作。

解码采用基于行列式的快速逆矩阵算法：通过预计算子矩阵行列式（在指数域上为加法），避免通用高斯消元，将 O(n^3) 的求逆简化为 O(n^2) 的矩阵-向量乘。

### 2.3 纠删能力与冗余

| 参数 | 含义 |
|------|------|
| `mpackets` | 消息包数（原始数据被分成 mpackets 个包） |
| `rpackets` | 冗余包数（编码产生的校验包数量） |
| `npackets` | 总包数 = mpackets + rpackets |

**恢复条件**：只要收到 ≥ `mpackets` 个包（无论消息包还是冗余包），即可完整恢复原始消息。

**冗余率** = `(npackets - mpackets) / mpackets` = `rpackets / mpackets`

**最大可容忍丢包率** = `rpackets / npackets`

---

## 3. 架构设计

### 3.1 模块结构

```
┌───────────────────────────────────────────────┐
│             rs_code.h  (公共 API)              │
├───────────────────────────────────────────────┤
│  rs_config_t    运行时参数配置                  │
│  rs_params_t    计算派生常量                    │
│  rs_ctx_t       库上下文（含 GF 查找表）        │
├───────────────────────────────────────────────┤
│  rs_init()      初始化上下文 + GF 表           │
│  rs_free()      释放资源                       │
│  rs_encode()    Cauchy RS 编码                 │
│  rs_decode()    Cauchy RS 解码                 │
│  rs_generate_message()  生成测试消息           │
│  rs_compare_message()   比较消息               │
│  rs_simulate_loss()     模拟丢包               │
└───────────────────────────────────────────────┘
```

### 3.2 数据流

```
               rs_encode()
message ─────────────────────→ packets
(uint32_t[])                   (uint32_t[])
  mlen 个字                    npackets × plentot 个字

               rs_simulate_loss()
packets ──────────────────────→ rec_packets
                                (uint32_t[])
                                nrec × plentot 个字

               rs_decode()
rec_packets ─────────────────→ rec_message
                                (uint32_t[])
                                mlen 个字
```

### 3.3 内存所有权

| 缓冲区 | 分配方 | 释放方 |
|--------|--------|--------|
| `message`, `packets`, `rec_packets`, `rec_message` | 调用者（`calloc`/`malloc`） | 调用者（`free`） |
| `rs_ctx_t` 内部表（`exptoFE`, `fetoExp`） | `rs_init()` | `rs_free()` |

库函数不会接管或释放调用者传入的缓冲区。

---

## 4. 构建

### 4.1 前置条件

- C11 编译器（clang / gcc）
- CMake 3.20+
- macOS 或 Linux

### 4.2 构建步骤

```bash
cd tools
mkdir -p build && cd build
cmake ..
cmake --build .
```

构建产物：

| 产物 | 说明 |
|------|------|
| `librs_code.a` | 重构后的统一库 |
| `librs_code_legacy.a` | 原始代码的静态库（兼容旧接口） |
| `driver` | 原始驱动程序（使用 legacy 库） |
| `driver_lib` | 新驱动程序（使用 rs_code 库） |
| `test/test_gf_field` | GF 初始化测试 |
| `test/test_encode_decode` | 编解码往返测试 |
| `test/test_edge_cases` | 边界条件测试 |

### 4.3 运行

```bash
# 原始驱动
./driver

# 新 API 驱动
./driver_lib
```

### 4.4 在其他 CMake 项目中集成

方式一：子目录

```cmake
add_subdirectory(path/to/tools rs_code_lib)
target_link_libraries(your_target PRIVATE rs_code)
```

方式二：安装后 find_package（需自行编写 Findrs_code.cmake）

---

## 5. API 参考

所有类型和函数声明在 `rs_code.h` 中，支持 C++ 调用（`extern "C"` 包装）。

### 5.1 类型

#### `rs_config_t` — 运行时配置

```c
typedef struct {
    int lfield;      /* log2 of Galois field size (1..15) */
    int nsegs;       /* number of segments per packet */
    int mpackets;    /* number of message packets */
    int rpackets;    /* number of redundant packets */
    int print_debug; /* non-zero to enable debug prints */
} rs_config_t;
```

| 字段 | 类型 | 范围 | 说明 |
|------|------|------|------|
| `lfield` | int | 1 ~ 15 | 有限域 GF(2^`lfield`) 的阶的对数。决定了域的大小和查找表规模。**约束**：`max(mpackets, rpackets) ≤ 2^(lfield-1)` |
| `nsegs` | int | ≥ 1 | 每个包中的段数。影响包的粒度。增大 `nsegs` 会增大包尺寸，减少包的头部开销占比 |
| `mpackets` | int | ≥ 1 | 消息包数量，即原始数据被划分的包数。同时也是恢复消息所需的最少包数 |
| `rpackets` | int | ≥ 1 | 冗余包数量。决定了最大可容忍丢包数 |
| `print_debug` | int | 0 或 1 | 是否在 `rs_encode`/`rs_decode` 中打印耗时等调试信息到 `stdout` |

默认值宏：

```c
#define RS_CONFIG_DEFAULTS { \
    .lfield    = 10,  \
    .nsegs     = 25,  \
    .mpackets  = 200, \
    .rpackets  = 200, \
    .print_debug = 1   \
}
```

使用默认值时：
- 域 = GF(2^10) = GF(1024)
- 包大小 = 4 × 25 × 10 = 1000 字节
- 消息大小 = 200 × 1000 = 200,000 字节
- 编码大小 = 400 × 1000 = 400,000 字节
- 冗余率 = 2.0x（可容忍 200 / 400 = 50% 丢包）

---

#### `rs_params_t` — 派生参数

```c
typedef struct {
    int npackets;     /* mpackets + rpackets */
    int mseglen;      /* mpackets * lfield */
    int plen;         /* nsegs * lfield      (payload words per packet) */
    int plentot;      /* plen + 1            (including index word) */
    int mlen;         /* plen * mpackets     (message length in words) */
    int elen;         /* plen * npackets     (encoding length in words) */
    int table_length; /* 1 << lfield */
    int smult_field;  /* table_length - 1 */
} rs_params_t;
```

这些值由 `rs_init()` 根据配置自动计算，调用者**无需手动设置**。在分配缓冲区时需读取这些值：

| 字段 | 公式 | 用途 |
|------|------|------|
| `npackets` | mpackets + rpackets | 编码产生的总包数 |
| `plen` | nsegs × lfield | 每包有效载荷字数（uint32_t） |
| `plentot` | plen + 1 | 每包总字数（含 1 个索引用字） |
| `mlen` | plen × mpackets | 消息缓冲区长（字数） |
| `elen` | plen × npackets | 编码总长（字数） |
| `table_length` | 2^lfield | GF 查找表长度 |
| `smult_field` | 2^lfield - 1 | 乘法群元素个数 |

字节大小 = 字数 × `sizeof(uint32_t)` = 字数 × 4。

---

#### `rs_ctx_t` — 库上下文

```c
typedef struct {
    rs_config_t cfg;
    rs_params_t par;

    /* Galois field tables (heap-allocated) */
    uint32_t *exptoFE;  /* [table_length + lfield] */
    uint32_t *fetoExp;  /* [table_length]           */
    uint32_t  colbit;
    uint32_t  bit[16];  /* BIT array, index 0..lfield-1 */
} rs_ctx_t;
```

- `cfg`：保存初始化时的配置副本
- `par`：派生参数，`rs_init()` 计算后只读
- `exptoFE`：指数 → 域元素映射表（堆分配）
- `fetoExp`：域元素 → 指数映射表（堆分配）
- `colbit`：Cauchy 矩阵偏移量，= 2^(lfield-1)
- `bit[i]`：单比特掩码数组，bit[i] = 2^i

调用者通常只读 `cfg` 和 `par`，不需要直接访问域运算表。

---

### 5.2 函数

#### `rs_init`

```c
int rs_init(rs_ctx_t *ctx, const rs_config_t *cfg);
```

初始化库上下文。分配 GF 查找表、计算所有派生参数。

**参数**：
- `ctx`：待初始化的上下文指针（栈分配或堆分配均可）
- `cfg`：配置参数指针

**返回值**：

| 值 | 含义 |
|----|------|
| 0 | 成功 |
| -1 | 无效配置（`lfield` 越界、`nsegs/mpackets/rpackets` ≤ 0、`max(mpackets,rpackets) > 2^(lfield-1)`、空指针） |
| -2 | 内存分配失败 |

**注意**：可以多次调用 `rs_init`（会先 `memset` 为零再填充），但更安全的做法是先 `rs_free` 再重新 `rs_init`。

---

#### `rs_free`

```c
void rs_free(rs_ctx_t *ctx);
```

释放上下文持有的所有堆内存，并将整个结构体清零。对已清零或 `NULL` 的上下文调用是安全的空操作。

**参数**：
- `ctx`：上下文指针。可以为 `NULL`（无操作）。

---

#### `rs_encode`

```c
void rs_encode(const rs_ctx_t *ctx, const uint32_t *message, uint32_t *packets);
```

对消息执行 Cauchy RS 编码，生成消息包 + 冗余包。

**参数**：
- `ctx`：已初始化的上下文（只读）
- `message`：输入消息，长度 ≥ `ctx->par.mlen` 个 `uint32_t`
- `packets`：输出缓冲区，长度 ≥ `ctx->par.npackets × ctx->par.plentot` 个 `uint32_t`

**输出格式**：
- `packets[i × plentot]`：包索引（0, 1, ..., npackets-1）
- `packets[i × plentot + 1 .. i × plentot + plentot - 1]`：包载荷
- 前 `mpackets` 个包包含原始消息数据
- 后 `rpackets` 个包包含冗余校验数据

**时间复杂度**：O(mpackets × rpackets × lfield^2 × nsegs)

**耗时统计**：当 `cfg.print_debug != 0` 时，向 stdout 输出编码耗时。

---

#### `rs_decode`

```c
int rs_decode(const rs_ctx_t *ctx, const uint32_t *rec_packets, int *nrec,
              uint32_t *rec_message);
```

从接收到的包子集中恢复原始消息。

**参数**：
- `ctx`：已初始化的上下文（只读）
- `rec_packets`：接收到的包，按 `plentot` 字一段连续存储。每个包以索引字开头（即编码时 `packets[i*plentot]` 处的值）。长度 ≥ `nrec × plentot` 个 `uint32_t`
- `nrec`：指向接收包数的指针。入口值必须 ≥ `mpackets` 才能成功恢复
- `rec_message`：输出缓冲区，长度 ≥ `ctx->par.mlen` 个 `uint32_t`

**返回值**：

| 值 | 含义 |
|----|------|
| 0 | 成功恢复 |
| 1 | 包不足（`*nrec < mpackets`） |
| -1 | 内部内存分配失败 |

**解码过程**：
1. 识别已接收的消息包，直接填入 `rec_message`
2. 缺失的消息包由冗余包通过 Cauchy 逆矩阵恢复
3. 内部使用行列式快速逆矩阵算法

**耗时统计**：当 `cfg.print_debug != 0` 时，向 stdout 输出解码耗时。

---

#### `rs_generate_message`

```c
void rs_generate_message(const rs_ctx_t *ctx, uint32_t *message);
```

用递增序列 `{0, 1, 2, ..., mlen-1}` 填充消息缓冲区。用于测试和基准测试。

**参数**：
- `ctx`：已初始化的上下文
- `message`：输出缓冲区，长度 ≥ `ctx->par.mlen`

---

#### `rs_compare_message`

```c
int rs_compare_message(const rs_ctx_t *ctx, const uint32_t *a, const uint32_t *b);
```

逐字比较两条消息，返回不匹配的字数。当 `cfg.print_debug != 0` 时，每个不匹配位置会输出到 stdout。

**参数**：
- `ctx`：已初始化的上下文
- `a`, `b`：待比较的消息，长度均 ≥ `ctx->par.mlen`

**返回值**：不匹配的字数（0 表示完全一致）。

---

#### `rs_simulate_loss`

```c
long rs_simulate_loss(const rs_ctx_t *ctx, const uint32_t *packets,
                      uint32_t *rec_packets, int *nrec, int loss_start);
```

从完整编码包中选取一个连续的 `mpackets` 包子集，模拟丢包场景。

**参数**：
- `ctx`：已初始化的上下文
- `packets`：完整编码包（`rs_encode` 的输出）
- `rec_packets`：输出缓冲区，长度 ≥ `mpackets × plentot`
- `nrec`：输出，接收到的包数（= `mpackets`）
- `loss_start`：保留的起始包索引（0-based）。传入 `-1` 表示使用默认中央选取策略：从 `(npackets - mpackets) / 2` 开始取 `mpackets` 个包

**返回值**：基于当前时间的伪随机种子（`tv_usec`），可用于复现测试。

**保留策略说明**：

| `loss_start` 值 | 行为 | 模拟场景 |
|------------------|------|----------|
| `-1` | 从中央保留 `mpackets` 个包 | 混合丢包（部分消息包 + 部分冗余包） |
| `0` | 保留前 `mpackets` 个包 | 零丢包（仅消息包，无冗余包） |
| `mpackets` | 保留第 `mpackets` ~ `2*mpackets-1` 个包 | 极端丢包（全部消息包丢失，仅冗余包） |

---

## 6. 使用示例

### 6.1 快速开始

最简完整示例——使用默认配置编解码：

```c
#include "rs_code.h"
#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    rs_ctx_t ctx;
    rs_config_t cfg = RS_CONFIG_DEFAULTS;
    cfg.print_debug = 0;  /* 关闭调试输出 */

    if (rs_init(&ctx, &cfg) != 0) {
        fprintf(stderr, "初始化失败\n");
        return 1;
    }

    /* 分配缓冲区 */
    uint32_t *message     = calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *rec_message = calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *packets     = calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_packets = calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));

    /* 编码 */
    rs_generate_message(&ctx, message);
    rs_encode(&ctx, message, packets);

    /* 模拟丢包：保留中央 mpackets 个包 */
    int nrec = 0;
    rs_simulate_loss(&ctx, packets, rec_packets, &nrec, -1);

    /* 解码 */
    int ret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
    if (ret == 0) {
        int miss = rs_compare_message(&ctx, message, rec_message);
        printf("解码完成，不匹配字数: %d\n", miss);
    } else {
        printf("解码失败，返回值: %d\n", ret);
    }

    /* 清理 */
    free(message); free(rec_message); free(packets); free(rec_packets);
    rs_free(&ctx);
    return 0;
}
```

### 6.2 自定义配置

配置一个小域、低冗余的场景：

```c
rs_config_t cfg = {
    .lfield     = 4,    /* GF(2^4) = GF(16) */
    .nsegs      = 2,    /* 每包 2 段 */
    .mpackets   = 4,    /* 4 个消息包 */
    .rpackets   = 4,    /* 4 个冗余包 → 50% 丢包容忍 */
    .print_debug = 0
};
```

对应的派生参数：
- 域大小 = 2^4 = 16
- 包有效载荷 = 2 × 4 = 8 字（32 字节）
- 消息大小 = 8 × 4 = 32 字（128 字节）
- 编码大小 = 8 × 8 = 64 字（256 字节）
- 每个包总大小 = (8 + 1) × 4 = 36 字节

### 6.3 指定丢包位置

```c
int nrec;

/* 场景 1：前一半消息包丢失，后一半和所有冗余包保留 */
rs_simulate_loss(&ctx, packets, rec_packets, &nrec, ctx.cfg.mpackets / 2);

/* 场景 2：所有消息包丢失，仅冗余包存活 —— 验证极端恢复能力 */
rs_simulate_loss(&ctx, packets, rec_packets, &nrec, ctx.cfg.mpackets);

/* 场景 3：无丢包，直接保留所有消息包 */
rs_simulate_loss(&ctx, packets, rec_packets, &nrec, 0);
```

### 6.4 使用自定义消息数据

```c
/* 不使用 rs_generate_message，填入实际数据 */
uint32_t *message = calloc(ctx.par.mlen, sizeof(uint32_t));

/* 将原始字节流按小端序读入 uint32_t 数组 */
const uint8_t *raw_data = /* ... */;
for (int i = 0; i < ctx.par.mlen; i++) {
    message[i] = ((uint32_t)raw_data[4*i])
               | ((uint32_t)raw_data[4*i+1] << 8)
               | ((uint32_t)raw_data[4*i+2] << 16)
               | ((uint32_t)raw_data[4*i+3] << 24);
}

rs_encode(&ctx, message, packets);
```

### 6.5 多次编解码循环

```c
rs_ctx_t ctx;
rs_config_t cfg = RS_CONFIG_DEFAULTS;
cfg.print_debug = 0;
rs_init(&ctx, &cfg);

for (int iter = 0; iter < 100; iter++) {
    uint32_t *message     = calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *rec_message = calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *packets     = calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_packets = calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));

    /* 用不同数据填充消息 */
    for (int i = 0; i < ctx.par.mlen; i++)
        message[i] = (uint32_t)(i + iter);

    rs_encode(&ctx, message, packets);

    int nrec = 0;
    rs_simulate_loss(&ctx, packets, rec_packets, &nrec, -1);

    if (rs_decode(&ctx, rec_packets, &nrec, rec_message) != 0)
        printf("迭代 %d 解码失败\n", iter);

    free(message); free(rec_message); free(packets); free(rec_packets);
}

rs_free(&ctx);
```

---

## 7. 参数配置指南

### 7.1 `lfield`（域大小）选择

| lfield | 域大小 | 查找表内存 | 最大 mpackets/rpackets | 适用场景 |
|--------|--------|-----------|----------------------|----------|
| 4 | 16 | 64 B | 8 | 最小化测试、教学 |
| 8 | 256 | 1 KB + 1 KB | 128 | 小规模数据 |
| 10 | 1024 | 4 KB + 4 KB | 512 | 默认，通用场景 |
| 12 | 4096 | 16 KB + 16 KB | 2048 | 大规模数据 |
| 15 | 32768 | 128 KB + 128 KB | 16384 | 极大规模 |

**关键约束**：`max(mpackets, rpackets) ≤ 2^(lfield-1)`

违反此约束时 `rs_init()` 返回 `-1`。

### 7.2 冗余率选择

| 配置 | 冗余率 | 可容忍丢包率 | 适用场景 |
|------|--------|-------------|----------|
| mpackets=16, rpackets=4 | 1.25x | 20% | 损伤风险低 |
| mpackets=16, rpackets=8 | 1.5x | 33% | 中等风险（推荐） |
| mpackets=200, rpackets=200 | 2.0x | 50% | 高风险（默认） |
| mpackets=8, rpackets=8 | 2.0x | 50% | 极端冗余 |
| mpackets=4, rpackets=12 | 4.0x | 75% | 极端冗余 |

### 7.3 `nsegs`（段数）选择

`nsegs` 影响包的粒度：

- **nsegs = 1**：最小包大小 = 4 × 1 × lfield 字节。适合带宽受限场景
- **nsegs ≥ 10**：较大包，减少索引开销占比，提高吞吐。适合存储/光盘场景

包大小（字节）= 4 × nsegs × lfield

### 7.4 常见配置模板

**光盘备份（本项目主要场景）**：

```c
rs_config_t cfg = {
    .lfield = 10, .nsegs = 25, .mpackets = 200, .rpackets = 200, .print_debug = 0
};
/* 消息 = 200 KB，编码 = 400 KB，包大小 = 1000 B，冗余率 2.0x */
```

**低延迟网络传输**：

```c
rs_config_t cfg = {
    .lfield = 8, .nsegs = 4, .mpackets = 32, .rpackets = 8, .print_debug = 0
};
/* 消息 = 4 KB，编码 = 5 KB，包大小 = 128 B，冗余率 1.25x */
```

**极限恢复能力**：

```c
rs_config_t cfg = {
    .lfield = 6, .nsegs = 8, .mpackets = 8, .rpackets = 24, .print_debug = 0
};
/* 消息 = 2 KB，编码 = 8 KB，冗余率 4.0x，容忍 75% 丢包 */
```

---

## 8. 数据布局

### 8.1 内存中的包格式

每个包在内存中占用 `plentot` 个 `uint32_t` 字：

```
┌──────────┬─────────────────────────────────────────────┐
│ 索引字    │ 有效载荷 (plen 个字)                        │
│ [0]      │ [1] [2] [3] ... [plen]                     │
│ packet_id│ line_0  line_1  line_2  ...  line_(plen-1) │
└──────────┴─────────────────────────────────────────────┘
 ◄── plentot 个 uint32_t ──►
```

- **索引字**（`packets[i * plentot]`）：包编号，0 ~ npackets-1。编码时由 `rs_encode` 自动写入，解码时用于识别该包是消息包还是冗余包
- **有效载荷**（`packets[i * plentot + 1]` ~ `packets[i * plentot + plen]`）：包的实际数据

### 8.2 编码包数组布局

编码后，所有包按编号连续存储：

```
packets[]:
┌─────────────┬─────────────┬     ┌─────────────┬─────────────┬     ┌─────────────┐
│  packet 0   │  packet 1   │ ... │packet M-1   │  packet M   │ ... │packet N-1   │
│ (message)   │ (message)   │     │ (message)   │ (redundant) │     │ (redundant) │
└─────────────┴─────────────┘     └─────────────┴─────────────┘     └─────────────┘
 ◄────── mpackets 个包 ──────►   ◄──────── rpackets 个包 ────────►
 ◄────────────────── npackets 个包 ──────────────────────────────►
```

每包占 `plentot` 个字。总数组大小 = `npackets × plentot` 个 `uint32_t`。

### 8.3 接收包数组布局

接收包数组的格式与编码包相同——连续的 `nrec` 个包，每个包 `plentot` 字，索引字保留包编号。缺失包直接跳过：

```
rec_packets[]:
┌─────────────┬─────────────┬     ┌─────────────┐
│  packet i   │  packet j   │ ... │  packet k   │
│ (received)  │ (received)  │     │ (received)  │
└─────────────┴─────────────┘     └─────────────┘
 ◄──────── nrec 个包，每个 plentot 字 ────────►
```

`rs_decode` 通过索引字判断每个包原本是消息包（索引 < mpackets）还是冗余包（索引 ≥ mpackets）。

### 8.4 消息数组布局

消息（`message` / `rec_message`）是一维 `uint32_t` 数组，长度为 `mlen = plen × mpackets`：

```
message[]:
┌──────────────────────┬──────────────────────┬     ┌──────────────────────┐
│  message packet 0    │  message packet 1    │ ... │  message packet M-1  │
│  (plen 个字)         │  (plen 个字)         │     │  (plen 个字)         │
└──────────────────────┴──────────────────────┘     └──────────────────────┘
 ◄──────────────────── mlen 个 uint32_t ──────────────────────────────────►
```

---

## 9. 集成指南

### 9.1 最小集成

只需两步：

1. 将 `rs_code.h` 和 `rs_code.c` 复制到项目中
2. 编译 `rs_code.c` 并链接

```cmake
add_library(rs_code STATIC rs_code.c)
target_include_directories(rs_code PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
```

### 9.2 编解码完整流程

```c
#include "rs_code.h"

/* 1. 配置 */
rs_config_t cfg = {
    .lfield = 10, .nsegs = 25,
    .mpackets = 200, .rpackets = 200,
    .print_debug = 0
};

/* 2. 初始化 */
rs_ctx_t ctx;
if (rs_init(&ctx, &cfg) != 0) { /* 处理错误 */ }

/* 3. 分配缓冲区（大小由 ctx.par 决定） */
uint32_t *msg    = calloc(ctx.par.mlen, sizeof(uint32_t));
uint32_t *pkt    = calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
uint32_t *recpkt = calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
uint32_t *recmsg = calloc(ctx.par.mlen, sizeof(uint32_t));

/* 4. 填充 message 并编码 */
/* ... your data into msg ... */
rs_encode(&ctx, msg, pkt);

/* 5. 传输/存储 pkt，接收端收到部分包到 recpkt */

/* 6. 解码 */
int nrec = /* 实际接收包数，必须 >= cfg.mpackets */;
int ret = rs_decode(&ctx, recpkt, &nrec, recmsg);
/* ret == 0 → recmsg 包含恢复的原始消息 */

/* 7. 清理 */
free(msg); free(pkt); free(recpkt); free(recmsg);
rs_free(&ctx);
```

### 9.3 与 Blu-ray Vault 项目的集成

按照项目路线图，本库对应 Phase 2（`liberasure`）的 Cauchy RS 部分。建议集成方式：

1. 将 `rs_code.c` 编译为 `liberasure` 的一个源文件
2. 在 `liberasure` 层面封装更高层的 API（如按 chunk 编解码、与 disc layout 的映射）
3. `lfield`、`mpackets`、`rpackets` 根据冗余等级动态选择：

```c
rs_config_t make_config(const char *level) {
    if (strcmp(level, "standard") == 0)
        return (rs_config_t){ .lfield=8,  .nsegs=25, .mpackets=16, .rpackets=4,  .print_debug=0 };
    if (strcmp(level, "high") == 0)
        return (rs_config_t){ .lfield=8,  .nsegs=25, .mpackets=16, .rpackets=8,  .print_debug=0 };
    if (strcmp(level, "extreme") == 0)
        return (rs_config_t){ .lfield=8,  .nsegs=25, .mpackets=8,  .rpackets=8,  .print_debug=0 };
    /* default */
    return (rs_config_t)RS_CONFIG_DEFAULTS;
}
```

### 9.4 C++ 调用

头文件已包含 `extern "C"` 保护，可直接在 C++ 中使用：

```cpp
#include "rs_code.h"
#include <vector>

class ErasureCoder {
    rs_ctx_t ctx_;
public:
    ErasureCoder(const rs_config_t& cfg) {
        if (rs_init(&ctx_, &cfg) != 0)
            throw std::runtime_error("rs_init failed");
    }
    ~ErasureCoder() { rs_free(&ctx_); }

    std::vector<uint32_t> encode(const std::vector<uint32_t>& msg) {
        std::vector<uint32_t> pkts(ctx_.par.npackets * ctx_.par.plentot);
        rs_encode(&ctx_, msg.data(), pkts.data());
        return pkts;
    }

    /* ... */
};
```

---

## 10. 测试

### 10.1 构建并运行测试

```bash
cd tools/build
cmake --build .
ctest --output-on-failure
```

### 10.2 测试套件说明

| 测试 | 文件 | 覆盖内容 |
|------|------|----------|
| **GF 初始化** | `test/test_gf_field.c` | 生命周期（init/free）、无效配置拒绝、GF 查找表往返一致性、多种 lfield 值、乘法单位元/colbit 验证 |
| **编解码往返** | `test/test_encode_decode.c` | 默认/小/中配置往返、纯冗余包恢复、纯消息包恢复、混合丢包、包不足失败、消息生成与比较一致性 |
| **边界条件** | `test/test_edge_cases.c` | 最小配置(1+1)、最大丢包容忍、零丢包、lfield=1、高冗余比(4+12)、空上下文 free、重复 init/free、nsegs=1 |

### 10.3 编写新测试

1. 在 `tools/test/` 下创建 `test_xxx.c`
2. 在 `tools/test/CMakeLists.txt` 中添加 `add_rs_test(test_xxx)`
3. 重新构建：`cmake --build .`

测试框架为简单的宏 + 返回值：

```c
static int passed = 0, failed = 0;
#define TEST_ASSERT(cond, msg) do { \
    if (cond) passed++; else { failed++; fprintf(stderr, "FAIL: %s\n", msg); } \
} while (0)

/* ... 测试逻辑 ... */

return failed > 0 ? 1 : 0;
```

---

## 11. 与原始代码的对比

| 方面 | 原始代码 | rs_code 库 |
|------|----------|-----------|
| 参数 | 编译时 `#define`（修改后重新编译） | 运行时 `rs_config_t`（可动态切换） |
| 组织 | 6 对 .c/.h 文件 + 1 个 driver | 单一 rs_code.h + rs_code.c |
| 上下文 | 全局/局部变量散落各处 | 统一 `rs_ctx_t` 上下文 |
| 内存管理 | 调用者分配所有大数组 | GF 表由 `rs_init` 内部分配，`rs_free` 释放 |
| 类型 | `typedef unsigned int UNSIGNED` | `uint32_t`（跨平台一致） |
| 错误处理 | `exit(434)` | 返回错误码（-1/-2/1） |
| 解码内存 | 内部 `malloc`，无释放（泄漏） | 内部 `calloc`，函数返回前 `free` |
| 丢包模拟 | 固定策略（中央保留） | 可指定起始位置 |
| 构建系统 | Makefile | CMake |
| 测试 | 无 | 3 个测试文件，CTest 集成 |
| 兼容性 | 原始文件完整保留，仍可通过 `librs_code_legacy.a` 使用 | 新旧代码共存 |

---

## 12. 局限性

1. **仅支持纠删（Erasure），不支持错误（Error）**：解码假设收到的包内容都是正确的。如果包内容被篡改或损坏，解码会产出错误结果但不会报错。如需错误检测，应在包级别添加 CRC/校验和

2. **无增量编码**：每次 `rs_encode` 必须对整条消息重新编码，不支持追加数据

3. **解码器内部临时内存**：`rs_decode` 在堆上分配约 `O(mpackets × lfield × nsegs)` 大小的临时空间，对于大规模配置可能较显著

4. **线程安全**：`rs_ctx_t` 不是线程安全的。多线程场景下，每个线程应持有独立的上下文

5. **无 SIMD 优化**：当前实现为标量 C 代码。高吞吐场景可通过 SSE/AVX/NEON 加速 XOR 运算

6. **丢包模拟简陋**：`rs_simulate_loss` 仅支持连续块选取。实际应用中需要随机丢包或按坏扇区模式丢包

---

参考论文：

> "An XOR-Based Erasure-Resilient Coding Scheme"
> Johannes Bloemer, Malik Kalfane, Marek Karpinski, Richard Karp, Michael Luby, David Zuckerman
> ICSI Technical Report TR-95-048
