@ freeze.s - Hold Sustain loads off: a preset saved with it on comes up with the block off and its footswitch unlit, as a press
@ that turned it off would leave them. Its Hold follows the block's on/off, and a block made by a preset load would grab before
@ it has any input. tools/features/freeze.py hooks the handlers before two calls of the preset load.
.syntax unified
.thumb
.include "freeze.inc"               @ FREEZE_ID: Hold Sustain's preset model ID (tools/features/freeze.py PRESET_ID)
.equ GRAPH, 0x28d92a99              @ () -> the block graph, as the footswitch toggle passes it
.equ MEMSET, 0x28e24b79             @ (p, value, n)
.equ BLOCK_INFO, 0x28e0fe95         @ (graph, block, &info[0x34]): the preset model ID at info + 1; an unknown block leaves it
.equ BYPASSED, 0x28e04515           @ (graph, block, &byte): 1 when bypassed; an unknown block leaves it
.equ COLOUR, 0x28e0f0ed             @ (graph, block, 1, &byte): the block's LED colour
.equ RGB, 0x28db7e1d                @ (colour, lit) -> its {r, g, b}
.equ REC_FX, 6                      @ a block record's type for an effect
.equ REC_ID, 6                      @ in a block record: its model's preset model ID, unaligned
.equ REC_ON, 0xf                    @ in a block record: on (1) or off (0)
.equ NODE_TYPE, 9                   @ in a footswitch node: 1 when it turns a block on and off
.equ NODE_BLOCK, 0xc
.equ NODE_LIT, 0x20
.equ NODE_RGB, 0x21
.equ INFO, 0x34

.thumb_func
.global freeze_rec_off
freeze_rec_off:                     @ before a preset load applies a block record (engine, location, record)
    ldrb r3, [r2]
    cmp r3, #REC_FX
    bne 1f
    ldr.w r3, [r2, #REC_ID]
    movw r12, #FREEZE_ID
    cmp r3, r12
    bne 1f
    movs r3, #0
    strb r3, [r2, #REC_ON]
1:  bx lr

.thumb_func
.global freeze_fs_unlit
freeze_fs_unlit:                    @ before a preset load puts a footswitch node in its list (list, node)
    ldrb r3, [r1, #NODE_TYPE]
    cmp r3, #1
    bne 9f
    ldrb.w r3, [r1, #NODE_LIT]
    cmp r3, #0
    beq 9f
    push {r4, lr}
    sub sp, #0x38                   @ the block info at sp, a byte at sp + INFO
    mov r4, r1
    mov r0, sp
    movs r1, #0
    movs r2, #0x38
    ldr r3, =MEMSET
    blx r3
    ldr r3, =GRAPH
    blx r3
    mov r2, sp
    ldr r1, [r4, #NODE_BLOCK]
    ldr r3, =BLOCK_INFO
    blx r3
    cmp r0, #0
    blt 8f
    ldr.w r3, [sp, #1]
    movw r2, #FREEZE_ID
    cmp r3, r2
    bne 8f
    ldr r3, =GRAPH
    blx r3
    add r2, sp, #INFO
    ldr r1, [r4, #NODE_BLOCK]
    ldr r3, =BYPASSED
    blx r3
    cmp r0, #0
    blt 8f
    ldrb.w r3, [sp, #INFO]
    cbz r3, 8f                      @ the block is on: the LED as saved
    movs r3, #0
    strb.w r3, [r4, #NODE_LIT]
    ldr r3, =GRAPH
    blx r3
    add r3, sp, #INFO
    movs r2, #1
    ldr r1, [r4, #NODE_BLOCK]
    ldr r12, =COLOUR
    blx r12
    ldrb.w r0, [sp, #INFO]
    movs r1, #0
    ldr r3, =RGB
    blx r3
    ldrh r3, [r0]
    ldrb r2, [r0, #2]
    strb.w r2, [r4, #NODE_RGB + 2]
    strh.w r3, [r4, #NODE_RGB]
8:  add sp, #0x38
    pop {r4, pc}
9:  bx lr
.ltorg
