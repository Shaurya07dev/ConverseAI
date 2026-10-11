import 'package:flutter/material.dart';

import '../../../app/theme.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            // subtle orange glow
            Positioned(
              top: -120,
              right: -100,
              child: Container(
                width: 300,
                height: 300,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: VaakSetuColors.orange.withValues(alpha: 0.08),
                ),
              ),
            ),

            
          ]
        )
      )
    );
  }
}